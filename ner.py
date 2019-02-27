# -*- coding:utf-8 -*-
import tensorflow as tf
import csv
import os
import sys
import collections

from sklearn.metrics import f1_score,precision_score,recall_score

from bert import tokenization
from bert import modeling
from bert import optimization

import tf_metrics

flags = tf.flags
FLAGS = flags.FLAGS


flags.DEFINE_string("vocab_file", None,
                    "The vocabulary file that the BERT model was trained on.")

flags.DEFINE_string(
    "data_dir", None,
    "The input datadir.",
)

flags.DEFINE_bool(
    "do_lower_case", True,
    "Whether to lower case the input text.")

flags.DEFINE_string(
    "init_checkpoint", None,
    "Initial checkpoint (usually from a pre-trained BERT model)."
)

flags.DEFINE_bool("use_tpu", False, "Whether to use TPU or GPU/CPU.")

flags.DEFINE_string(
    "bert_config_file", None,
    "The config json file corresponding to the pre-trained BERT model."
)

flags.DEFINE_bool(
    "do_train", False,
    "Whether to train.")

flags.DEFINE_bool(
    "do_eval", False,
    "Whether to train.")

flags.DEFINE_bool(
    "do_predict", False,
    "Whether to predict.")

flags.DEFINE_bool(
    "do_test", False,
    "Whether to test.")

flags.DEFINE_string(
    "output_dir", None,
    "The output directory where the model checkpoints will be written.")

flags.DEFINE_integer(
    "max_seq_length", 128,
    "The maximum total input sequence length after WordPiece tokenization.")

flags.DEFINE_integer(
    "num_tpu_cores", 8,
    "Only used if `use_tpu` is True. Total number of TPU cores to use.")

flags.DEFINE_float(
    "warmup_proportion", 0.1,
    "Proportion of training to perform linear learning rate warmup for. "
    "E.g., 0.1 = 10% of training.")

flags.DEFINE_float("num_train_epochs", 3.0, "Total number of training epochs to perform.")

flags.DEFINE_integer("train_batch_size", 25, "Total batch size for training.")

flags.DEFINE_float("learning_rate", 5e-5, "The initial learning rate for Adam.")

flags.DEFINE_integer("eval_batch_size", 8, "Total batch size for eval.")

flags.DEFINE_integer("predict_batch_size", 8, "Total batch size for predict.")

tf.flags.DEFINE_string("master", None, "[Optional] TensorFlow master URL.")

flags.DEFINE_integer("save_checkpoints_steps", 1000,
                     "How often to save the model checkpoint.")

flags.DEFINE_integer("iterations_per_loop", 1000,
                     "How many steps to make in each estimator call.")

class InputExample(object):
  """A single training/test example for simple sequence classification."""

  def __init__(self, guid, text, label=None):
    """Constructs a InputExample.

    Args:
      guid: Unique id for the example.
      text_a: string. The untokenized text of the first sequence. For single
        sequence tasks, only this sequence must be specified.
      text_b: (Optional) string. The untokenized text of the second sequence.
        Only must be specified for sequence pair tasks.
      label: (Optional) string. The label of the example. This should be
        specified for train and dev examples, but not for test examples.
    """
    self.guid = guid
    self.text = text
    self.label = label

class PaddingInputExample(object):
  """Fake example so the num input examples is a multiple of the batch size.

  When running eval/predict on the TPU, we need to pad the number of examples
  to be a multiple of the batch size, because the TPU requires a fixed batch
  size. The alternative is to drop the last batch, which is bad because it means
  the entire output data won't be generated.

  We use this class instead of `None` because treating `None` as padding
  battches could cause silent errors.
  """

class InputFeatures(object):
    """A single set of features of data."""

    def __init__(self, input_ids, input_mask, segment_ids, label_ids, real_label_len):
        self.input_ids = input_ids
        self.input_mask = input_mask
        self.segment_ids = segment_ids
        self.label_ids = label_ids
        self.real_label_len = real_label_len
        #self.label_mask = label_mask

def file_based_input_fn_builder(input_file, seq_length, is_training, drop_remainder):
    name_to_features = {
        "input_ids": tf.FixedLenFeature([seq_length], tf.int64),
        "input_mask": tf.FixedLenFeature([seq_length], tf.int64),
        "segment_ids": tf.FixedLenFeature([seq_length], tf.int64),
        "label_ids": tf.FixedLenFeature([seq_length], tf.int64),
        "real_label_len": tf.FixedLenFeature([1], tf.int64),
        #"real_label_len": tf.FixedLenFeature([], tf.int64),
        # "label_ids":tf.VarLenFeature(tf.int64),
        #"label_mask": tf.FixedLenFeature([seq_length], tf.int64),
    }

    def _decode_record(record, name_to_features):
        example = tf.parse_single_example(record, name_to_features)
        for name in list(example.keys()):
            t = example[name]
            if t.dtype == tf.int64:
                t = tf.to_int32(t)
            example[name] = t
        return example

    def input_fn(params):
        batch_size = params["batch_size"]
        d = tf.data.TFRecordDataset(input_file)
        if is_training:
            d = d.repeat()
            d = d.shuffle(buffer_size=100)
        d = d.apply(tf.contrib.data.map_and_batch(
            lambda record: _decode_record(record, name_to_features),
            batch_size=batch_size,
            drop_remainder=drop_remainder
        ))
        return d
    return input_fn

def convert_single_example(ex_index, example, label_list, max_seq_length,
                           tokenizer, mode = None):
  """Converts a single `InputExample` into a single `InputFeatures`."""

  label_map = {}
  for (i, label) in enumerate(label_list):
    label_map[label] = i

  #print("=============================================================")
  #print(example.text)
  #print(example.label)

  text_tokens = example.text.split(' ')
  label_tokens = example.label.split(' ')
  #print(text_tokens)
  #print(label_tokens)

  tokens = []
  labels = []

  #deal first seq
  for one_token in text_tokens:
      tokens.append(one_token)

  if len(tokens) >= max_seq_length - 1:
      tokens = tokens[0 : max_seq_length - 2]

  #deal second seq
  for one_token in label_tokens:
      labels.append(one_token)
  
  if len(labels) >= max_seq_length - 1:
      labels = labels[0 : max_seq_length - 2]

  ntokens = []
  segment_ids = []
  label_ids = []
  ntokens.append("[CLS]")
  segment_ids.append(0)
  label_ids.append(label_map["[CLS]"])

  #add first seq
  for one_token in tokens:
      one_token = tokenizer.tokenize(one_token)
      ntokens.append(one_token[0])
      segment_ids.append(0)
  ntokens.append("[SEP]")
  segment_ids.append(0)

  #add second seq
  for one_token in labels:
    try:
        label_ids.append(label_map[one_token])
    except:
        print("========chg=======")
        print(label_tokens)
  label_ids.append(label_map["[SEP]"])

  #print("=====chg_tokens========================================================")
  #print(ntokens)

  input_ids = tokenizer.convert_tokens_to_ids(ntokens)
  input_mask = [1] * len(input_ids)

  #add padding
  while len(input_ids) < max_seq_length:
    input_ids.append(0)
    input_mask.append(0)
    segment_ids.append(0)
    ntokens.append("**NULL**")
  #add padding
  while len(label_ids) < max_seq_length:
    label_ids.append(0)
  
  real_label_len = [get_real_labels(label_ids)]

  feature = InputFeatures(
    input_ids = input_ids,
    input_mask = input_mask,
    segment_ids = segment_ids,
    label_ids = label_ids,
    real_label_len = real_label_len,
  )

  #print(ntokens)
  #print(input_ids)
  #print(input_mask)
  #print(segment_ids)
  #print(labels)
  #print(label_ids)
  #print(real_label_len)
  #print

  return feature

def file_based_convert_examples_to_features(
    examples, label_list, max_seq_length, tokenizer, output_file, mode = None):
    """处理训练数据"""
    writer = tf.python_io.TFRecordWriter(output_file)
    for (ex_index, example) in enumerate(examples):
        #print(ex_index)
        if ex_index % 5000 == 0:
            tf.logging.info("Writing example %d of %d" %(ex_index, len(examples)))
        feature = convert_single_example(ex_index, example, label_list, max_seq_length, tokenizer, mode)

        def create_int_feature(values):
            f = tf.train.Feature(int64_list=tf.train.Int64List(value=list(values)))
            return f

        features = collections.OrderedDict()
        features['input_ids'] = create_int_feature(feature.input_ids)
        features['input_mask'] = create_int_feature(feature.input_mask)
        features['segment_ids'] = create_int_feature(feature.segment_ids)
        features['label_ids'] = create_int_feature(feature.label_ids)
        features['real_label_len'] = create_int_feature(feature.real_label_len)

        tf_example = tf.train.Example(features=tf.train.Features(feature=features))
        writer.write(tf_example.SerializeToString())

def get_real_labels(labels):
    """
    获取实际需要计算loss的维度
    """
    length = 0
    for id in labels:
        length += 1
        if id == 102:
            break
    return length

def create_model(bert_config, is_training, input_ids, input_mask,
                 segment_ids, labels, num_labels, real_label_len, use_one_hot_embeddings):
    model = modeling.BertModel(
        config = bert_config,
        is_training = is_training,
        input_ids = input_ids,
        input_mask = input_mask,
        token_type_ids = segment_ids,
        use_one_hot_embeddings = use_one_hot_embeddings
    )

    #vocab_size
    #vocab_size = 21128

    #(25, 20, 768)
    output_layer = model.get_sequence_output()

    hidden_size = output_layer.shape[-1].value

    output_weights = tf.get_variable(
        "output_weights", [num_labels, hidden_size],
        initializer=tf.truncated_normal_initializer(stddev=0.02))

    output_bias = tf.get_variable(
        "output_bias", [num_labels], initializer=tf.zeros_initializer())
    
    with tf.variable_scope("loss"):
        if is_training:
            output_layer = tf.nn.dropout(output_layer, keep_prob = 0.9)

        #Tensor("IteratorGetNext:3", shape=(25, 1), dtype=int32)
        #print("chg===============================")
        #print(tf.reshape(real_label_len, [-1]))

        #slice output
        #output_layer = tf.strided_slice(output_layer, [0, 0, 0], [FLAGS.train_batch_size, tf.reshape(real_label_len, [-1]), hidden_size])

        output_layer = tf.reshape(output_layer, [-1, hidden_size])
        logits = tf.matmul(output_layer, output_weights, transpose_b = True)
        logits = tf.nn.bias_add(logits, output_bias)
        logits = tf.reshape(logits, [-1, FLAGS.max_seq_length, num_labels])

        log_probs = tf.nn.log_softmax(logits, axis = -1)

        #slice labels
        #labels = tf.slice(labels, [0, 0], [FLAGS.train_batch_size, real_len])
        #Tensor("loss/Neg:0", shape=(25, 20), dtype=float32)
        #Tensor("loss/Sum_1:0", shape=(), dtype=float32)

        one_hot_labels = tf.one_hot(labels, depth = num_labels, dtype = tf.float32)
        per_example_loss = -tf.reduce_sum(one_hot_labels * log_probs, axis = -1)
        loss = tf.reduce_sum(per_example_loss)

        probabilities = tf.nn.softmax(logits, axis = -1)
        predict = tf.argmax(probabilities, axis = -1)

        return (loss, per_example_loss, logits, predict)

def model_fn_builder(bert_config, num_labels, init_checkpoint, learning_rate,
                     num_train_steps, num_warmup_steps, use_tpu, use_one_hot_embeddings):
    def model_fn(features, labels, mode, params):
        for name in sorted(features.keys()):
            tf.logging.info("name = %s, shape = %s" % (name, features[name].shape)) 

        input_ids = features['input_ids']
        input_mask = features['input_mask']
        segment_ids = features['segment_ids']
        label_ids = features['label_ids']
        real_label_len = features['real_label_len']

        is_training = (mode == tf.estimator.ModeKeys.TRAIN)

        (total_loss, per_example_loss, logits, predicts) = create_model(
            bert_config, is_training, input_ids, input_mask, segment_ids, label_ids, num_labels, real_label_len, use_one_hot_embeddings)
        tvars = tf.trainable_variables()
        scaffold_fn = None

        #tf.logging.info("total loss is : %s" %(total_loss))

        if init_checkpoint:
            (assignment_map, initialized_variable_names) = modeling.get_assignment_map_from_checkpoint(tvars,init_checkpoint)
            tf.train.init_from_checkpoint(init_checkpoint, assignment_map)
            if use_tpu:
                def tpu_scaffold():
                    tf.train.init_from_checkpoint(init_checkpoint, assignment_map)
                    return tf.train.Scaffold()
                scaffold_fn = tpu_scaffold
            else:
                tf.train.init_from_checkpoint(init_checkpoint, assignment_map)
        tf.logging.info("**** Trainable Variables ****")

        for var in tvars:
            init_string = ""
            if var.name in initialized_variable_names:
                init_string = ", *INIT_FROM_CKPT*"
            tf.logging.info("  name = %s, shape = %s%s", var.name, var.shape,
                            init_string)

        logging_hook = tf.train.LoggingTensorHook({"loss": total_loss}, every_n_iter=10)

        output_spec = None
        if mode == tf.estimator.ModeKeys.TRAIN:
            train_op = optimization.create_optimizer(
                total_loss, learning_rate, num_train_steps, num_warmup_steps, use_tpu)
            output_spec = tf.contrib.tpu.TPUEstimatorSpec(
                mode=mode,
                loss=total_loss,
                train_op=train_op,
                training_hooks=[logging_hook],
                scaffold_fn=scaffold_fn)
        elif mode == tf.estimator.ModeKeys.EVAL:
            
            def metric_fn(per_example_loss, label_ids, logits):
                predictions = tf.argmax(logits, axis=-1, output_type=tf.int32)
                precision = tf_metrics.precision(label_ids,predictions,11,[2,3,4,5,6,7],average="macro")
                recall = tf_metrics.recall(label_ids,predictions,11,[2,3,4,5,6,7],average="macro")
                f = tf_metrics.f1(label_ids,predictions,11,[2,3,4,5,6,7],average="macro")

                return {
                    "eval_precision":precision,
                    "eval_recall":recall,
                    "eval_f": f,
                }

            eval_metrics = (metric_fn, [per_example_loss, label_ids, logits])

            output_spec = tf.contrib.tpu.TPUEstimatorSpec(
                mode=mode,
                loss=total_loss,
                eval_metrics=eval_metrics,
                scaffold_fn=scaffold_fn)
        else:
            output_spec = tf.contrib.tpu.TPUEstimatorSpec(
                mode = mode,predictions= predicts,scaffold_fn=scaffold_fn
            )
        return output_spec
    return model_fn

class DataProcessor(object):
  """Base class for data converters for sequence classification data sets."""

  def get_train_examples(self, data_dir):
    """Gets a collection of `InputExample`s for the train set."""
    raise NotImplementedError()

  def get_dev_examples(self, data_dir):
    """Gets a collection of `InputExample`s for the dev set."""
    raise NotImplementedError()

  def get_test_examples(self, data_dir):
    """Gets a collection of `InputExample`s for prediction."""
    raise NotImplementedError()

  def get_labels(self):
    """Gets the list of labels for this data set."""
    raise NotImplementedError()

  @classmethod
  def _read_data(cls, input_file, quotechar=None):
    """Reads a tab separated value file."""
    with tf.gfile.Open(input_file, "r") as f:
      reader = csv.reader(f, delimiter="\t", quotechar=quotechar)
      lines = []
      for line in reader:
        lines.append((line[0], line[1]))
        #print(line[0], line[1])
      #print(lines)
      return lines

def read_ner_data(input_file):
    """Reads a BIO data."""
    with open(input_file) as f:
        lines = []
        words = []
        labels = []
        for line in f:
            contends = line.strip()
            word = line.strip().split(' ')[0]
            label = line.strip().split(' ')[-1]

            if len(contends) == 0:
                l = ' '.join([label for label in labels if len(label) > 0])
                w = ' '.join([word for word in words if len(word) > 0])
                lines.append([l, w])
                words = []
                labels = []
                continue
            words.append(word)
            labels.append(label)
        return lines

class NerProcessor(DataProcessor):
    def get_train_examples(self, data_dir):
        return self._create_example(
            read_ner_data(os.path.join(data_dir, "train.txt")), "train"
        )

    def get_dev_examples(self, data_dir):
        return self._create_example(
            read_ner_data(os.path.join(data_dir, "dev.txt")), "dev"
        )

    def get_test_examples(self, data_dir):
        return self._create_example(
            read_ner_data(os.path.join(data_dir, "test.txt")), "test")

    def get_labels(self, label_path):
        label_list = []
        with open(label_path) as f:
            for line in f.readlines():
                label = line.rstrip()
                label_list.append(label)
        return label_list

    def _create_example(self, lines, set_type):
        examples = []
        for (i, line) in enumerate(lines):
            guid = "%s-%s" % (set_type, i)
            text = tokenization.convert_to_unicode(line[1])
            label = tokenization.convert_to_unicode(line[0])
            examples.append(InputExample(guid=guid, text=text, label=label))
        return examples

class Seq2SeqProcessor(DataProcessor):
  def get_train_examples(self, data_dir):
      return self._create_example(
          #self._read_data(os.path.join(data_dir, "test_data")), "train")
          self._read_data(os.path.join(data_dir, "train.txt")), "train")

  def get_dev_examples(self, data_dir):
      return self._create_example(
          self._read_data(os.path.join(data_dir, "dev.txt")), "dev")

  def get_test_examples(self,data_dir):
      return self._create_example(
          self._read_data(os.path.join(data_dir, "test.txt")), "test")


  def get_labels(self, data_path):
      """get all labels"""
      label_list = []
      #with open("chinese_L-12_H-768_A-12/vocab.txt") as f:
      with open(data_path) as f:
          for line in f.readlines():
              line = line.rstrip()
              label_list.append(line)
      return label_list

  def _create_example(self, lines, set_type):
      examples = []
      for (i, line) in enumerate(lines):
          guid = "%s-%s" % (set_type, i)
          text = tokenization.convert_to_unicode(line[0])
          label = tokenization.convert_to_unicode(line[1])
          examples.append(InputExample(guid=guid, text=text, label=label))
      return examples

def main(_):
    tf.logging.set_verbosity(tf.logging.INFO)
    tokenizer = tokenization.FullTokenizer(
        vocab_file=FLAGS.vocab_file, do_lower_case=FLAGS.do_lower_case)

    processors = {
      "seq2seq": Seq2SeqProcessor,
      "ner" : NerProcessor
    }

    task_name = "ner"
    processor = processors[task_name]()
    label_list = processor.get_labels("./data_ner/all_labels")
    print(label_list)

    tpu_cluster_resolver = None
    if FLAGS.use_tpu and FLAGS.tpu_name:
        tpu_cluster_resolver = tf.contrib.cluster_resolver.TPUClusterResolver(
            FLAGS.tpu_name, zone=FLAGS.tpu_zone, project=FLAGS.gcp_project)

    is_per_host = tf.contrib.tpu.InputPipelineConfig.PER_HOST_V2

    run_config = tf.contrib.tpu.RunConfig(
        cluster=tpu_cluster_resolver,
        master=FLAGS.master,
        model_dir=FLAGS.output_dir,
        save_checkpoints_steps=FLAGS.save_checkpoints_steps,
        tpu_config=tf.contrib.tpu.TPUConfig(
            iterations_per_loop=FLAGS.iterations_per_loop,
            num_shards=FLAGS.num_tpu_cores,
            per_host_input_for_training=is_per_host))

    bert_config = modeling.BertConfig.from_json_file(FLAGS.bert_config_file)

    train_examples = None
    num_train_steps = None
    num_warmup_steps = None

    if FLAGS.do_train:
        train_examples = processor.get_train_examples("./data_ner/")
        """
        for one_ex in train_examples:
            print(one_ex.text)
            print(one_ex.label)
        """

        num_train_steps = int(
            len(train_examples) / FLAGS.train_batch_size * FLAGS.num_train_epochs)
        num_warmup_steps = int(num_train_steps * FLAGS.warmup_proportion)

    model_fn = model_fn_builder(
        bert_config=bert_config,
        num_labels=len(label_list),
        init_checkpoint=FLAGS.init_checkpoint,
        learning_rate=FLAGS.learning_rate,
        num_train_steps=num_train_steps,
        num_warmup_steps=num_warmup_steps,
        use_tpu=FLAGS.use_tpu,
        use_one_hot_embeddings=FLAGS.use_tpu)

    estimator = tf.contrib.tpu.TPUEstimator(
        use_tpu=FLAGS.use_tpu,
        model_fn=model_fn,
        config=run_config,
        train_batch_size=FLAGS.train_batch_size,
        eval_batch_size=FLAGS.eval_batch_size,
        predict_batch_size=FLAGS.predict_batch_size)

    if FLAGS.do_train:
        train_file = os.path.join(FLAGS.output_dir, "train.tf_record")
        file_based_convert_examples_to_features(train_examples, label_list, FLAGS.max_seq_length, tokenizer, train_file)
        tf.logging.info("***** Running training *****")
        tf.logging.info("  Num examples = %d", len(train_examples))
        tf.logging.info("  Batch size = %d", FLAGS.train_batch_size)
        tf.logging.info("  Num steps = %d", num_train_steps)
        train_input_fn = file_based_input_fn_builder(
            input_file=train_file,
            seq_length=FLAGS.max_seq_length,
            is_training=True,
            drop_remainder=True)
        estimator.train(input_fn=train_input_fn, max_steps=num_train_steps)

    if FLAGS.do_predict:
        token_path = os.path.join(FLAGS.output_dir, "token_test.txt")

        #with open('./output/label2id.pkl','rb') as rf:
        #    label2id = pickle.load(rf)
        #    id2label = {value:key for key,value in label2id.items()}

        id2label = dict()
        with open("./data_ner/all_labels") as f:
            n = 0
            for line in f.readlines():
                token = line.rstrip()
                id2label[n] = token
                n += 1
        
        if os.path.exists(token_path):
            os.remove(token_path)

        predict_examples = processor.get_test_examples("./data_ner/")
        print("======================================begin================")
        for one_ex in predict_examples:
            print(one_ex.text)
            print(one_ex.label)
        print("======================================end================")

        predict_file = os.path.join(FLAGS.output_dir, "predict.tf_record")
        file_based_convert_examples_to_features(predict_examples, label_list,
                                                 FLAGS.max_seq_length, tokenizer,
                                                 predict_file, mode="test")
                            
        tf.logging.info("***** Running prediction*****")
        tf.logging.info("  Num examples = %d", len(predict_examples))
        tf.logging.info("  Batch size = %d", FLAGS.predict_batch_size)
        if FLAGS.use_tpu:
            # Warning: According to tpu_estimator.py Prediction on TPU is an
            # experimental feature and hence not supported here
            raise ValueError("Prediction in TPU not supported")
        predict_drop_remainder = True if FLAGS.use_tpu else False
        predict_input_fn = file_based_input_fn_builder(
            input_file=predict_file,
            seq_length=FLAGS.max_seq_length,
            is_training=False,
            drop_remainder=predict_drop_remainder)

        result = estimator.predict(input_fn=predict_input_fn)
        #for elem in result:
        #    print(elem)
        output_predict_file = os.path.join(FLAGS.output_dir, "label_test.txt")
        with open(output_predict_file,'w') as writer:
            for prediction in result:
                #print(prediction)
                output_line = " ".join(id2label[id] for id in prediction if id!=0) + "\n"
                #print(output_line)
                writer.write(output_line)

    if FLAGS.do_eval:
        eval_examples = processor.get_dev_examples(FLAGS.data_dir)
        eval_file = os.path.join(FLAGS.output_dir, "eval.tf_record")
        file_based_convert_examples_to_features(
            eval_examples, label_list, FLAGS.max_seq_length, tokenizer, eval_file)

        tf.logging.info("***** Running evaluation *****")
        tf.logging.info("  Num examples = %d", len(eval_examples))
        tf.logging.info("  Batch size = %d", FLAGS.eval_batch_size)
        eval_steps = None
        if FLAGS.use_tpu:
            eval_steps = int(len(eval_examples) / FLAGS.eval_batch_size)
        eval_drop_remainder = True if FLAGS.use_tpu else False
        eval_input_fn = file_based_input_fn_builder(
            input_file=eval_file,
            seq_length=FLAGS.max_seq_length,
            is_training=False,
            drop_remainder=eval_drop_remainder)
        result = estimator.evaluate(input_fn=eval_input_fn, steps=eval_steps)
        output_eval_file = os.path.join(FLAGS.output_dir, "eval_results.txt")
        with open(output_eval_file, "w") as writer:
            tf.logging.info("***** Eval results *****")
            for key in sorted(result.keys()):
                tf.logging.info("  %s = %s", key, str(result[key]))
                writer.write("%s = %s\n" % (key, str(result[key])))

if __name__ == "__main__":
    flags.mark_flag_as_required("vocab_file")
    tf.app.run()