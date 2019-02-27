# bert_ner

### 注意
1. 因为需要padding，需要在预测的label中增加一个[PAD]字符 & 要放在第一个位置，这样就直接在代码里添加编号0, 参考data/all_labels
2. 下载模型chinese_L-12_H-768_A-12
3. 下载bert源代码

### 效果
```python
INFO:tensorflow:  eval_f = 0.9632821
INFO:tensorflow:  eval_precision = 0.9651096
INFO:tensorflow:  eval_recall = 0.96164674
INFO:tensorflow:  global_step = 6078
INFO:tensorflow:  loss = 16.909075
```

