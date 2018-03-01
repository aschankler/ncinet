"""
Model specific constructor functions.
"""

import tensorflow as tf
import numpy as np

from .config_meta import SessionConfig, EvalWriterBase
from .config_hyper import EncoderConfig, InfConfig
from .ncinet_input import inputs

from typing import List, Tuple, Any


class EncoderSessionConfig(SessionConfig):
    xent_type = 'sigmoid'
    model_config = EncoderConfig()

    @property
    def batch_gen_args(self):
        return {'eval_data': False, 'batch_size': self.train_config.batch_size, 'data_types': ['fingerprints']}

    def logits_network_gen(self, graph, config, eval_net=False):
        # type: (tf.Graph, EncoderConfig, bool) -> Tuple[tf.Tensor, tf.Tensor]
        with graph.as_default():
            # Fingerprint placeholders
            prints = tf.placeholder(tf.float32, shape=[None, 100, 100, 1], name="prints")
            labels = tf.placeholder(tf.float32, shape=[None, 100, 100, 1], name="labels")

            # Calculate logits and loss
            from .model import autoencoder
            logits = autoencoder(prints, config)

            return logits, labels

    def eval_metric(self, logits, labels):
        """Calculate norm of the difference of original and output."""
        norms = tf.norm(tf.subtract(labels, logits), ord="fro", axis=[1, 2])
        eval_op = tf.divide(norms, 100 * 100)
        # eval_op = tf.divide(tf.reduce_sum(norms), 100 * 100)
        return eval_op

    def batch_gen(self):
        def add_noise(x, factor):
            import numpy as np
            noise = np.random.randn(*x.shape)
            x = x + factor * noise
            return np.clip(x, 0., 1.)

        batch_gen = inputs(**self.batch_gen_args)

        def wrapped_gen():
            while True:
                prints = next(batch_gen)[0]
                labels = prints
                prints = add_noise(prints, 0.1)
                yield prints, labels

        return wrapped_gen()


class InfSessionConfig(SessionConfig):
    xent_type = 'softmax'
    inf_type = None             # type: str

    def logits_network_gen(self, graph, config, eval_net=False):
        # type: (tf.Graph, InfConfig, bool) -> Tuple[tf.Tensor, tf.Tensor]
        with graph.as_default():
            # Fingerprint placeholders
            prints = tf.placeholder(tf.float32, shape=[None, 100, 100, 1], name="prints")

            # Placeholders and preprocessing for labels.
            labels_input = tf.placeholder(tf.int32, shape=[None], name="labels")

            if not eval_net:
                if self.inf_type == "topo":
                    labels = tf.one_hot(labels_input, 4, dtype=tf.float32)
                elif self.inf_type == "sign":
                    labels_index = tf.floordiv(tf.add(tf.cast(tf.sign(labels_input), tf.int32), 1), 2)
                    labels = tf.one_hot(labels_index, 2, dtype=tf.float32)
                else:
                    raise ValueError
            else:
                labels = labels_input

            # Calculate logits
            from .model import inf_classify
            logits = inf_classify(prints, config)

            return logits, labels

    def eval_metric(self, logits, labels):
        """Calculate precision @1"""
        # Convert stability score to one_hot (x > 0)
        if self.inf_type == "sign":
            labels = tf.floordiv(tf.add(tf.sign(labels), 1), 2)

        labels = tf.cast(labels, tf.int32)
        top_k = tf.nn.in_top_k(logits, labels, 1)
        # eval_op = tf.count_nonzero(top_k)
        return top_k

    def batch_gen(self):
        return inputs(**self.batch_gen_args)


class EvalWriter(EvalWriterBase):
    """Stores data from eval runs"""
    def __init__(self, archive_name, archive_dir, saved_vars):
        # type: (str, str, Tuple[str]) -> None
        self.archive_name = archive_name
        self.archive_dir = archive_dir
        self.activation_names = saved_vars
        self.activation_ops = None      # type: List[tf.Tensor, ...]

        # Accumulators for captured data
        self.activation_acc = []
        self.inputs_acc = []

        # freeze the class
        EvalWriterBase.__init__(self)

    def setup(self, sess):
        """Setup writer using the the current session"""
        # type: tf.Session -> None
        self.activation_ops = [sess.graph.get_tensor_by_name(op_name) for op_name in self.activation_names]

    @property
    def data_ops(self):
        # type: () -> List[tf.Tensor, ...]
        """Ops to evaluate and store at each run"""
        return self.activation_ops

    @data_ops.setter
    def data_ops(self, ops):
        # type: (Tuple[np.ndarray, ...]) -> None
        self.activation_acc.append(ops)

    def collect_batch(self, batch):
        # type: (Tuple[Any, ...]) -> None
        """Collect data used in eval"""
        self.inputs_acc.append(batch)

    def collect_vars(self, sess):
        # type: (tf.Session) -> None
        """Save trained variables"""
        import os
        from .layers import NciKeys
        file_name = os.path.join(self.archive_dir, 'vars.npz')

        scope = []
        for key in [NciKeys.INF_VARIABLES, NciKeys.AE_DECODER_VARIABLES, NciKeys.AE_ENCODER_VARIABLES]:
            scope += sess.graph.get_collection(key)

        trained_vars = {var.op.name: var.eval(sess) for var in scope}

        with open(file_name, 'w') as vars_file:
            np.savez(vars_file, **trained_vars)

    def save(self):
        """Save the data collected throughout evaluation"""
        import os
        file_name = os.path.join(self.archive_dir, self.archive_name + '.npz')

        # assemble the collected data
        names = ['results', 'names', 'fingerprints', 'topologies']
        names.extend(self.activation_names)

        input_data = map(np.concatenate, zip(*self.inputs_acc))
        act_data = map(np.concatenate, zip(*self.activation_acc))

        results = dict(zip(names, list(input_data) + list(act_data)))

        # save the file
        with open(file_name, 'wb') as result_file:
            np.savez(result_file, **results)


class TopoSessionConfig(InfSessionConfig):
    inf_type = 'topo'
    model_config = InfConfig()

    @property
    def batch_gen_args(self):
        return {'eval_data': False, 'batch_size': self.train_config.batch_size,
                'data_types': ['fingerprints', 'topologies']}


class SignSessionConfig(InfSessionConfig):
    inf_type = 'sign'
    model_config = InfConfig(n_logits=2)

    @property
    def batch_gen_args(self):
        return {'eval_data': False, 'batch_size': self.train_config.batch_size,
                'data_types': ['fingerprints', 'scores']}