import tensorflow as tf
import gym

from baselines.common import tf_util
from baselines.a2c.utils import fc
from baselines.common.distributions import make_pdtype
from baselines.common.input import observation_placeholder, encode_observation
from baselines.common.tf_util import adjust_shape
from baselines.common.models import get_network_builder


class PolicyWithValue(object):
    """
    Encapsulates fields and methods for RL policy and value function estimation with shared parameters
    """

    def __init__(self,
                 env,
                 observations,
                 latent,
                 estimate_q=False,
                 vf_latent=None,
                 sess=None,
                 **tensors):
        """TODO

        Parameters
        ----------
        env             RL environment

        observations    tensorflow placeholder in which the observations will be fed

        latent          latent state from which policy distribution parameters should be inferred

        vf_latent       latent state from which value function should be inferred (if None, then latent is used)

        sess            tensorflow session to run calculations in (if None, default session is used)

        **tensors       tensorflow tensors for additional attributes such as state or mask

        """
        self.X = observations
        self.state = tf.constant([])
        self.initial_state = None
        self.__dict__.update(tensors)

        vf_latent = vf_latent if vf_latent is not None else latent

        vf_latent = tf.layers.flatten(vf_latent)
        latent = tf.layers.flatten(latent)

        # Based on the action space, will select what probability distribution
        # type
        self.pdtype = make_pdtype(env.action_space)

        self.pd, self.pi = self.pdtype.pdfromlatent(latent, init_scale=0.01)

        # Take an action
        self.action = self.pd.sample()

        # Calculate the neg log of our probability
        self.neglogp = self.pd.neglogp(self.action)
        self.sess = sess or tf.get_default_session()

        if estimate_q:
            assert isinstance(env.action_space, gym.spaces.Discrete)
            self.q = fc(vf_latent, 'q', env.action_space.n)
            self.vf = self.q
        else:
            self.vf = fc(vf_latent, 'vf', 1)
            self.vf = self.vf[:, 0]

    def _evaluate(self, variables, observation, **extra_feed):
        sess = self.sess
        feed_dict = {self.X: adjust_shape(self.X, observation)}
        for inpt_name, data in extra_feed.items():
            if inpt_name in self.__dict__.keys():
                inpt = self.__dict__[inpt_name]
                if isinstance(inpt, tf.Tensor) and \
                        inpt._op.type == 'Placeholder':
                    feed_dict[inpt] = adjust_shape(inpt, data)

        return sess.run(variables, feed_dict)

    def step(self, obs, **extra_feed):
        """Compute next action(s) given the observation(s).

        Parameters
        ----------
        obs : array_like
            observation data (either single or a batch)

        Returns
        -------
        array_like
            action
        array_like
            value estimate
        array_like
            next state
        array_like
            negative log likelihood of the action under current policy
            parameters) tuple
        """
        a, v, state, neglogp = self._evaluate(
            [self.action, self.vf, self.state, self.neglogp],
            obs,
            **extra_feed
        )
        if state.size == 0:
            state = None
        return a, v, state, neglogp

    def value(self, obs, *args, **kwargs):
        """Compute value estimate(s) given the observation(s).

        Parameters
        ----------
        obs : array_like
            observation data (either single or a batch)

        Returns
        -------
        array_like
            value estimate
        """
        return self._evaluate(self.vf, obs, *args, **kwargs)

    def save(self, save_path):
        tf_util.save_state(save_path, sess=self.sess)

    def load(self, load_path):
        tf_util.load_state(load_path, sess=self.sess)


def build_policy(env,
                 policy_network,
                 value_network=None,
                 estimate_q=False,
                 **policy_kwargs):
    """TODO

    :param env:
    :param policy_network:
    :param value_network:
    :param estimate_q:
    :param policy_kwargs:
    :return:
    """
    print(env,
                 policy_network,
                 value_network,
                 estimate_q,
                 policy_kwargs)
    if isinstance(policy_network, str):
        network_type = policy_network
        policy_network = get_network_builder(network_type)(**policy_kwargs)

    def policy_fn(nbatch=None, nsteps=None, sess=None, observ_placeholder=None):
        ob_space = env.observation_space

        obs_ph = observ_placeholder if observ_placeholder is not None else \
            observation_placeholder(ob_space, batch_size=nbatch)

        extra_tensors = {}

        encoded_x = encode_observation(ob_space, obs_ph)

        # Create the actor network.
        with tf.compat.v1.variable_scope('pi', reuse=tf.compat.v1.AUTO_REUSE):
            policy_latent = policy_network(encoded_x)

        # Create a separate value function.
        with tf.compat.v1.variable_scope('vf', reuse=tf.compat.v1.AUTO_REUSE):
            vf_latent = policy_network(encoded_x)

        policy = PolicyWithValue(
            env=env,
            observations=obs_ph,
            latent=policy_latent,
            vf_latent=vf_latent,
            sess=sess,
            estimate_q=estimate_q,
            **extra_tensors
        )
        return policy

    return policy_fn
