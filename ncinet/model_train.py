"""
Constructs parts of the graph only used in training.
"""

import tensorflow as tf

# TODO: these numbers are not correct. Should be set in ncinet_input
NUM_EXAMPLES_PER_EPOCH_FOR_TRAIN = 12000
NUM_EXAMPLES_PER_EPOCH_FOR_EVAL = 600
BATCH_SIZE = 32

# TODO: enable learning rate decay
# Constants describing the training process.
MOVING_AVERAGE_DECAY = 0.9999     # The decay to use for the moving average.
NUM_EPOCHS_PER_DECAY = 350.0      # Epochs after which learning rate decays.
LEARNING_RATE_DECAY_FACTOR = 0.05  # Learning rate decay factor.
INITIAL_LEARNING_RATE = 0.005       # Initial learning rate.


def loss(logits, labels):
    """Sums L2Loss for trainable variables.
    Add summary for "Loss" and "Loss/avg".
    Args:
        logits: Logits from inference().
        labels: Labels from distorted_inputs or inputs(). Shape should match logits.
    Returns:
        Loss tensor of type float.
    """

    # record labels
    tf.summary.histogram("labels", labels)
    tf.summary.histogram("logits", tf.nn.sigmoid(logits))

    # batch entropy
    x_ent = tf.nn.sigmoid_cross_entropy_with_logits(logits=logits, labels=labels, name="entropy_per_ex")
    x_ent_mean = tf.reduce_mean(x_ent, name="cross_entropy")
    tf.add_to_collection('losses', x_ent_mean)

    # The total loss is the cross entropy loss plus all of the weight decay terms (L2 loss).
    return tf.add_n(tf.get_collection('losses'), name='total_loss')


def _add_loss_summaries(total_loss):
    """Add summaries for losses.
    Generates moving average for all losses and associated summaries for
    visualizing the performance of the network.
    Args:
        total_loss: Total loss from loss().
    Returns:
        loss_averages_op: op for generating moving averages of losses.
    """
    # Compute the moving average of all individual losses and the total loss.
    loss_averages = tf.train.ExponentialMovingAverage(0.9, name='loss_avg')
    losses = tf.get_collection('losses')

    loss_averages_op = loss_averages.apply(losses + [total_loss])

    # Write summary for total loss
    tf.summary.scalar("Total loss", total_loss)
    tf.summary.scalar("Total loss (avg)", loss_averages.average(total_loss))

    # Attach a scalar summary to all individual losses and averages.
    for l in losses:
        # Name each loss as '(raw)' and name the moving average version of the loss
        # as the original loss name.
        tf.summary.scalar(l.op.name + ' (raw)', l)
        tf.summary.scalar(l.op.name + ' (avg)', loss_averages.average(l))

    return loss_averages_op


def train(total_loss, global_step):
    """Train the model.
    Create an optimizer and apply to all trainable variables. Add moving
    average for all trainable variables.
    Args:
        total_loss: Total loss from loss().
        global_step: Integer Variable counting the number of training steps
          processed.
    Returns:
        train_op: op for training.
    """

    # Variables that affect learning rate.
    #num_batches_per_epoch = NUM_EXAMPLES_PER_EPOCH_FOR_TRAIN / BATCH_SIZE
    #decay_steps = int(num_batches_per_epoch * NUM_EPOCHS_PER_DECAY)

    # Decay the learning rate exponentially based on the number of steps.
    #lr = tf.train.exponential_decay(INITIAL_LEARNING_RATE,
    #                                global_step,
    #                                decay_steps,
    #                                LEARNING_RATE_DECAY_FACTOR,
    #                                staircase=True)
    lr = tf.constant(INITIAL_LEARNING_RATE, name="learning_rate")
    tf.summary.scalar('learning_rate', lr)

    # Generate moving averages of all losses and associated summaries.
    loss_averages_op = _add_loss_summaries(total_loss)

    # Compute gradients.
    with tf.control_dependencies([loss_averages_op]):
        opt = tf.train.AdamOptimizer(lr)
        grads = opt.compute_gradients(total_loss)

    # Apply gradients.
    apply_gradient_op = opt.apply_gradients(grads, global_step=global_step)

    # Add histograms for trainable variables.
    for var in tf.trainable_variables():
        tf.summary.histogram(var.op.name, var)

    # Add histograms for gradients.
    for grad, var in grads:
        if grad is not None:
            tf.summary.histogram(var.op.name + '/gradients', grad)

    # Track the moving averages of all trainable variables.
    #variable_averages = tf.train.ExponentialMovingAverage(
    #    MOVING_AVERAGE_DECAY, global_step)
    #variables_averages_op = variable_averages.apply(tf.trainable_variables())

    with tf.control_dependencies([apply_gradient_op]):
        train_op = tf.no_op(name='train')

    return train_op