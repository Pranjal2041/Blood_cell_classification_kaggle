# /k5wang-volume/Blood_cell_classification_kaggle/kaggle/BCCD_Dataset/BCCD_410
# |   + ---BASOPHIL  
# |   + ---EOSINOPHIL  
# |   + ---LYMPHOCYTE  
# |   + ---MONOCYTE  
# |   + ---NEUTROPHIL

# ARCHITECTURES = [
#     PBC_DARTS_OFF, PBC_DARTS_LPT,
#     PBC_PDARTS_OFF, PBC_PDARTS_LPT
# ]

# MODEL_PATHS = [
    # ./eval-PBC-darts-off-*/weights.pt, ./eval-PBC-darts-lpt-*/weights.pt
    # ./eval-PBC-pdarts-off-*/weights.pt, ./eval-PBC-pdarts-lpt*/weights.pt
# ]

# --batch_size = 8 --layer = 12

# ----
DIR = '/k5wang-volume/Blood_cell_classification_kaggle/kaggle/BCCD_Dataset/BCCD_410'
cd DIR

# Organize Data Dir
org_dir () {
    mv EOSINOPHIL 0_eosinophil
    mv LYMPHOCYTE 1_lymphocyte
    mv MONOCYTE 2_monocyte
    mv NEUTROPHIL 3_neutrophil
    mv BASOPHIL basophil
    mkdir erythroblast
    mkdir ig 
    mkdir platelet
}

cd PBC_dataset_split/PBC_dataset_split/Train && pwd
org_dir
cd ../Test && pwd
org_dir
cd ../Val && pwd
org_dir

cd /k5wang-volume/Blood_cell_classification_kaggle/darts-LPT
python test.py --model_path ./eval-BC-50-300-PBC-20210831-183328/weights.pt --arch DARTS_TS_BC_50EPOCH --batch_size 8 --layers 12 
