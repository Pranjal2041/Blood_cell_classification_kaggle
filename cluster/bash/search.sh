# Setting up working dir
echo Start Copying
SECONDS=0
cp -r /k5wang-volume/Blood_cell_classification_kaggle/kaggle /local/kaggle
cd /k5wang-volume/Blood_cell_classification_kaggle/darts-LPT
pwd
echo Copying DONE.
duration=$SECONDS
echo "$(($duration / 60)) minutes and $(($duration % 60)) seconds elapsed."

python train_search_ts.py --batch_size 3 --epochs 50 --save BC-50Epoch 

