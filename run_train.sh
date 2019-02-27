#!/bin/bash
source ~/.bashrc

if [[ ! -d ./output_t ]]; then
    mkdir output_t
fi

CUDA_VISIBLE_DEVICES=3 python_chg seq2seq.py --vocab_file="chinese_L-12_H-768_A-12/vocab.txt" \
                                             --do_train=true \
                                             --output_dir="./output" \
                                             --bert_config_file=chinese_L-12_H-768_A-12/bert_config.json \
                                             --init_checkpoint=chinese_L-12_H-768_A-12/bert_model.ckpt \
                                             --do_train=true
