#!/bin/bash

if [ $# -eq 0 ]; then
  echo "No arguments provided."
  echo "フォルダと同じ階層にこのshellスクリプトを置いてください。"
  echo "xx.sh <foldername>で実行できます。"
else
  echo $1 > $1/folder.txt

  # Dataset slug preparation
  modified_string=$(echo $1 | sed 's/\///g' | sed 's/\./-/g')
  modified_string=${modified_string:0:50}
  modified_string2=$(echo $modified_string | sed 's/_/-/g' | sed 's/\./-/g')
  modified_string2=${modified_string2/done-/}
  modified_string2=${modified_string2:0:50}
  
  # Check if dataset already exists
  if ! kaggle datasets status $modified_string2 >/dev/null 2>&1; then
    echo "Dataset does not exist. Initializing and creating..."
    # Init and create dataset since it does not exist
    kaggle datasets init -p $1
    # Apply modifications to dataset-metadata.json
    sed -i "s/INSERT_TITLE_HERE/$modified_string/g" $1/dataset-metadata.json
    sed -i "s/INSERT_SLUG_HERE/$modified_string2/g" $1/dataset-metadata.json
    kaggle datasets create -p $1 --dir-mode zip
    echo "Dataset created successfully."
  else
    echo "Dataset already exists. Updating..."
    # Update the dataset
    kaggle datasets version -p $1 --dir-mode zip -m "Update dataset"
    echo "Dataset updated successfully."
  fi
fi

# kaggle competitions submit -c waveform-inversion -f submission.csv -m "done_exp002_v001_subsample02_epoch30_huber_cosine_lr1e-4"