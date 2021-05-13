# RNA-SECONDARY-STRUCTURE-PREDICTION-BY-LEARNING-UNROLLED-ALGORITHMS

## Reproduced from ICLR 2020 paper titled "RNA SECONDARY STRUCTURE PREDICTION BY LEARNING UNROLLED ALGORITHMS"

ICLR Submission: https://openreview.net/forum?id=S1eALyrYDH

This paper proposed a model called 'E2Efold' which is an end-to-end deep learning model to predict the secondary structure of a sequence of RNA. E2Efold model consists of two networks: Deep Score model and Post-processing network. Then it used an unrolled algorithm for constrained programming as the template for deep architectures to enforce constraints. 

## Data

Datasets used could be downloaded by this link.
https://drive.google.com/drive/folders/19KPRYJjjMJh1qdMhtmUoYA_ncw3ocAHc

## Running Experiments

First you could consider to create the same environment by running the following command.

    Conda env create -f environment.yml

Then you could navigate to  '/experiment_ranstralign' folder and test the model we trained on RNAStralign test set by running the following command.

    python e2e_learning_stage3.py -c config.json --test True
    
You you could navigate to '/experiment_archiveii' folder and test the model we trained on ArchiveII test set by running the followning command.

    python e2e_learning_stage3.py -c config.json




## Team members:

- Yihui Wu (yw12g20)

- Mingjun Xie (mx2n20)

- Nihui Pan (np1n20)

- Hongshi Zhang (hz1y20)

