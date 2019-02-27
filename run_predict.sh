#!/bin/bash
source ~/.bashrc

CUDA_VISIBLE_DEVICES=7 python_chg seq2seq.py --vocab_file="chinese_L-12_H-768_A-12/vocab.txt" \
                                             --do_train=true \
                                             --output_dir="./output" \
	                                         --bert_config_file=chinese_L-12_H-768_A-12/bert_config.json \
	                                         --vocab_file=chinese_L-12_H-768_A-12/vocab.txt  \
	                                         --init_checkpoint=chinese_L-12_H-768_A-12/bert_model.ckpt \
                                             --do_train=false \
                                             --do_predict=true \
                                             --data_dir="./data_ner/"
