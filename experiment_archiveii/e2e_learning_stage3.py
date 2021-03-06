from torch.utils import data

from e2efold.models import ContactNetwork, ContactNetwork_test, ContactNetwork_fc
from e2efold.models import ContactAttention, ContactAttention_simple_fix_PE
from e2efold.models import Lag_PP_NN, RNA_SS_e2e, Lag_PP_zero, Lag_PP_perturb
from e2efold.models import Lag_PP_mixed, ContactAttention_simple
from e2efold.common.utils import *
from e2efold.common.config import process_config


if __name__ == '__main__':
    args = get_args()

    config_file = args.config

    config = process_config(config_file)
    print("#####Stage 3#####")
    print('Here is the configuration of this run: ')
    print(config)

    os.environ["CUDA_VISIBLE_DEVICES"]= config.gpu

    d = config.u_net_d
    BATCH_SIZE = config.BATCH_SIZE
    OUT_STEP = config.OUT_STEP
    LOAD_MODEL = config.LOAD_MODEL
    pp_steps = config.pp_steps
    pp_loss = config.pp_loss
    data_type = config.data_type
    model_type = config.model_type
    pp_type = '{}_s{}'.format(config.pp_model, pp_steps)
    rho_per_position = config.rho_per_position
    model_path = '../models_ckpt/supervised_{}_{}_d{}_l3.pt'.format(model_type, data_type,d)
    pp_model_path = '../models_ckpt/lag_pp_{}_{}_{}_position_{}.pt'.format(
        pp_type, data_type, pp_loss,rho_per_position)
    e2e_model_path = '../models_ckpt/e2e_{}_{}_d{}_{}_{}_position_{}.pt'.format(model_type,
        pp_type,d, data_type, pp_loss,rho_per_position)
    epoches_third = config.epoches_third
    evaluate_epi = config.evaluate_epi
    step_gamma = config.step_gamma
    k = config.k


    steps_done = 0
    # if gpu is to be used
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # seed everything for reproduction
    seed_torch(0)


    # for loading data
    # loading the rna ss data, the data has been preprocessed
    # 5s data is just a demo data, which do not have pseudoknot, will generate another data having that
    from e2efold.data_generator import RNASSDataGenerator, Dataset
    import collections
    RNA_SS_data = collections.namedtuple('RNA_SS_data',
        'seq ss_label length name pairs')

    test_data = RNASSDataGenerator('../data/{}/'.format(config.test_data_type), 'all_600')

    # Only checked the overlaped data type
    checked_type = ['RNaseP', '5s', 'tmRNA', 'tRNA', 'telomerase', '16s']


    seq_len = test_data.data_y.shape[-2]
    print('Max seq length ', seq_len)

    # using the pytorch interface to parallel the data generation and model training
    # params = {'batch_size': BATCH_SIZE,
    #           'shuffle': True,
    #           'num_workers': 6,
    #           'drop_last': True}
    # only for save the final results
    params = {'batch_size': 1,
              'shuffle': False,
              'num_workers': 0,
              'drop_last': False}
    test_set = Dataset(test_data)
    test_generator = data.DataLoader(test_set, **params)

    # seq_len =500

    # store the intermidiate activation

    activation = {}
    def get_activation(name):
        def hook(model, input, output):
            activation[name] = output.detach()
        return hook

    if model_type =='test_lc':
        contact_net = ContactNetwork_test(d=d, L=seq_len).to(device)
    if model_type == 'att6':
        contact_net = ContactAttention(d=d, L=seq_len).to(device)
    if model_type == 'att_simple':
        contact_net = ContactAttention_simple(d=d, L=seq_len).to(device)
    if model_type == 'att_simple_fix':
        contact_net = ContactAttention_simple_fix_PE(d=d, L=seq_len,
            device=device).to(device)
    if model_type == 'fc':
        contact_net = ContactNetwork_fc(d=d, L=seq_len).to(device)
    if model_type == 'conv2d_fc':
        contact_net = ContactNetwork(d=d, L=seq_len).to(device)

    # contact_net.conv1d2.register_forward_hook(get_activation('conv1d2'))

    # need to write the class for the computational graph of lang pp
    if pp_type=='nn':
        lag_pp_net = Lag_PP_NN(pp_steps, k).to(device)
    if 'zero' in pp_type:
        lag_pp_net = Lag_PP_zero(pp_steps, k).to(device)
    if 'perturb' in pp_type:
        lag_pp_net = Lag_PP_perturb(pp_steps, k).to(device)
    if 'mixed'in pp_type:
        lag_pp_net = Lag_PP_mixed(pp_steps, k, rho_per_position).to(device)

    if LOAD_MODEL and os.path.isfile(model_path):
        print('Loading u net model...')
        contact_net.load_state_dict(torch.load(model_path))
    if LOAD_MODEL and os.path.isfile(pp_model_path):
        print('Loading pp model...')
        lag_pp_net.load_state_dict(torch.load(pp_model_path))


    rna_ss_e2e = RNA_SS_e2e(contact_net, lag_pp_net)

    if LOAD_MODEL and os.path.isfile(e2e_model_path):
        print('Loading e2e model...')
        rna_ss_e2e.load_state_dict(torch.load(e2e_model_path))


    def save_prediction():
        contact_net.eval()
        lag_pp_net.eval()

        final_result_dict = dict()

        # for long sequences
        batch_n = 0
        for contacts, seq_embeddings, matrix_reps, seq_lens in test_generator:
            if batch_n % 10==0:
                print('Batch number: ', batch_n)

            contacts_batch = torch.Tensor(contacts.float()).to(device)
            seq_embedding_batch = torch.Tensor(seq_embeddings.float()).to(device)
            matrix_reps_batch = torch.unsqueeze(
                torch.Tensor(matrix_reps.float()).to(device), -1)

            state_pad = torch.zeros(1,2,2).to(device)

            PE_batch = get_pe(seq_lens, contacts.shape[-1]).float().to(device)
            with torch.no_grad():
                pred_contacts = contact_net(PE_batch,
                    seq_embedding_batch, state_pad)
                a_pred_list = lag_pp_net(pred_contacts, seq_embedding_batch)

            # the learning pp result
            final_pred = (a_pred_list[-1].cpu()>0.5).float()
            f1_tmp = list(map(lambda i: F1_low_tri(final_pred.cpu()[i],
                contacts_batch.cpu()[i]), range(contacts_batch.shape[0])))

            ct_tmp = contact2ct(final_pred[0].cpu().numpy(),
                seq_embeddings[0].cpu().numpy(), seq_lens.numpy()[0])
            true_ct_tmp = contact2ct(contacts_batch[0].cpu().numpy(),
                seq_embeddings[0].cpu().numpy(), seq_lens.numpy()[0])

            result_dict = dict()
            result_dict['name'] = test_data.data[batch_n].name
            result_dict['f1'] = f1_tmp[0]
            result_dict['pred_ct'] = ct_tmp
            result_dict['true_ct'] = true_ct_tmp

            final_result_dict[test_data.data[batch_n].name] = result_dict

            batch_n += 1
        # with open('../results/archiveii_short_prediction_dict.pickle', 'wb') as f:
        #     pickle.dump(final_result_dict, f)


    def per_family_evaluation():
        contact_net.eval()
        lag_pp_net.eval()
        result_no_train = list()
        result_no_train_shift = list()
        result_pp = list()
        result_pp_shift = list()

        f1_no_train = list()
        f1_pp = list()
        seq_lens_list = list()

        batch_n = 0
        for contacts, seq_embeddings, matrix_reps, seq_lens in test_generator:
            if batch_n %10==0:
                print('Batch number: ', batch_n)
            batch_n += 1
            contacts_batch = torch.Tensor(contacts.float()).to(device)
            seq_embedding_batch = torch.Tensor(seq_embeddings.float()).to(device)
            matrix_reps_batch = torch.unsqueeze(
                torch.Tensor(matrix_reps.float()).to(device), -1)

            state_pad = torch.zeros(contacts.shape).to(device)

            PE_batch = get_pe(seq_lens, contacts.shape[-1]).float().to(device)
            with torch.no_grad():
                pred_contacts = contact_net(PE_batch,
                    seq_embedding_batch, state_pad)
                a_pred_list = lag_pp_net(pred_contacts, seq_embedding_batch)

            # the learning pp result
            final_pred = (a_pred_list[-1].cpu()>0.5).float()
            result_tmp = list(map(lambda i: evaluate_exact(final_pred.cpu()[i],
                contacts_batch.cpu()[i]), range(contacts_batch.shape[0])))
            result_pp += result_tmp

            result_tmp_shift = list(map(lambda i: evaluate_shifted(final_pred.cpu()[i],
                contacts_batch.cpu()[i]), range(contacts_batch.shape[0])))
            result_pp_shift += result_tmp_shift

            f1_tmp = list(map(lambda i: F1_low_tri(final_pred.cpu()[i],
                contacts_batch.cpu()[i]), range(contacts_batch.shape[0])))
            f1_pp += f1_tmp
            seq_lens_list += list(seq_lens)


        pp_exact_p,pp_exact_r,pp_exact_f1 = zip(*result_pp)
        pp_shift_p,pp_shift_r,pp_shift_f1 = zip(*result_pp_shift)

        e2e_result_df = pd.DataFrame()
        e2e_result_df['name'] = [a.name for a in test_data.data]
        e2e_result_df['type'] = list(map(lambda x: x.split('_')[0], [a.name for a in test_data.data]))
        e2e_result_df['seq_lens'] = list(map(lambda x: x.numpy(), seq_lens_list))
        e2e_result_df['exact_p'] = pp_exact_p
        e2e_result_df['exact_r'] = pp_exact_r
        e2e_result_df['exact_f1'] = pp_exact_f1
        e2e_result_df['shift_p'] = pp_shift_p
        e2e_result_df['shift_r'] = pp_shift_r
        e2e_result_df['shift_f1'] = pp_shift_f1
        # pdb.set_trace()
        final_result = e2e_result_df[e2e_result_df['type'].isin(
            ['RNaseP', '5s', 'tmRNA', 'tRNA', 'telomerase', '16s'])]
        to_output = list(map(str,
            list(final_result[['exact_p', 'exact_r', 'exact_f1', 'shift_p','shift_r', 'shift_f1']].mean().values.round(3))))
        print('Number of sequences: ', len(final_result))
        print(to_output)


    per_family_evaluation()







