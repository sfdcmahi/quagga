import quagga
import numpy as np
from unittest import TestCase
from quagga.matrix import Matrix
from quagga.context import Context
from quagga.blocks import NpLstmRnn
from quagga.connector import Connector
from quagga.blocks import LogisticRegressionCe


class TestNpLstmRnn(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rng = np.random.RandomState(seed=42)
        cls.N = 10

    @classmethod
    def get_random_array(cls, shape=None):
        if not shape:
            shape = cls.rng.random_integers(7000, size=2)
        a = cls.rng.normal(0, 1, shape)
        u, _, v = np.linalg.svd(a, full_matrices=False)
        a = u if u.shape == shape else v
        return a.astype(dtype=np.float32)

    @classmethod
    def get_orthogonal_initializer(cls, nrows, ncols):
        shape = (nrows, ncols)
        def initializer():
            a = cls.rng.normal(0.0, 1.0, shape)
            u, _, v = np.linalg.svd(a, full_matrices=False)
            q = u if u.shape == shape else v
            q = q.reshape(shape).astype(np.float32)
            return q
        initializer.nrows = shape[0]
        initializer.ncols = shape[1]
        return initializer

    def test_fprop(self):
        """
        compare `fprop` results for cpu and gpu backends
        """
        r = []
        for i in xrange(self.N):
            nrows, ncols = self.rng.random_integers(2000, size=2)
            max_input_sequence_len = self.rng.random_integers(1000)
            x = 4 * self.rng.rand(ncols, max_input_sequence_len).astype(dtype=np.float32) - 2

            W = []
            for k in xrange(4):
                W.append(self.get_random_array((nrows, ncols)))
            def W_init():
                W_init.wk = (W_init.wk + 1) % 4
                return W[W_init.wk]
            W_init.wk = -1
            W_init.nrows = nrows
            W_init.ncols = ncols

            R = []
            for k in xrange(4):
                R.append(self.get_random_array((nrows, nrows)))
            def R_init():
                R_init.rk = (R_init.rk + 1) % 4
                return R[R_init.rk]
            R_init.rk = -1
            R_init.nrows = nrows
            R_init.ncols = nrows

            quagga.processor_type = 'gpu'
            x_gpu = Connector(Matrix.from_npa(x))
            np_lstm_rnn_gpu = NpLstmRnn(W_init, R_init, x_gpu, learning=False)
            np_lstm_rnn_gpu.fprop()
            np_lstm_rnn_gpu.context.synchronize()
            h_gpu = np_lstm_rnn_gpu.h.to_host()

            quagga.processor_type = 'cpu'
            x_cpu = Connector(Matrix.from_npa(x))
            np_lstm_rnn_cpu = NpLstmRnn(W_init, R_init, x_cpu, learning=False)
            np_lstm_rnn_cpu.fprop()
            np_lstm_rnn_cpu.context.synchronize()
            h_cpu = np_lstm_rnn_cpu.h.to_host()

            r.append(np.allclose(h_gpu, h_cpu, rtol=1e-7, atol=1e-3))

        self.assertEqual(sum(r), self.N)

    def test_bprop(self):
        """
        compare `bprop` results for cpu and gpu backends
        """
        r = []
        for i in xrange(self.N):
            nrows, ncols = self.rng.random_integers(2000, size=2)
            max_input_sequence_len = self.rng.random_integers(1000)
            x = 4 * self.rng.rand(ncols, max_input_sequence_len).astype(dtype=np.float32) - 2

            W = []
            for k in xrange(4):
                W.append(self.get_random_array((nrows, ncols)))
            def W_init():
                W_init.wk = (W_init.wk + 1) % 4
                return W[W_init.wk]
            W_init.wk = -1
            W_init.nrows = nrows
            W_init.ncols = ncols

            R = []
            for k in xrange(4):
                R.append(self.get_random_array((nrows, nrows)))
            def R_init():
                R_init.rk = (R_init.rk + 1) % 4
                return R[R_init.rk]
            R_init.rk = -1
            R_init.nrows = nrows
            R_init.ncols = nrows

            quagga.processor_type = 'gpu'
            context = Context()
            x_gpu = Connector(Matrix.from_npa(x), context, context)
            np_lstm_rnn_gpu = NpLstmRnn(W_init, R_init, x_gpu)
            h, dL_dh = np_lstm_rnn_gpu.h.register_usage(context, context)
            np_lstm_rnn_gpu.fprop()
            random_matrix = np.random.rand(dL_dh.nrows, dL_dh.ncols)
            Matrix.from_npa(random_matrix, 'float').copy(context, dL_dh)
            np_lstm_rnn_gpu.bprop()
            np_lstm_rnn_gpu.context.synchronize()
            dL_dW_gpu = np_lstm_rnn_gpu.dL_dW.to_host()
            dL_dR_gpu = np_lstm_rnn_gpu.dL_dR.to_host()
            dL_dx_gpu = np_lstm_rnn_gpu.dL_dx.to_host()

            quagga.processor_type = 'cpu'
            context = Context()
            x_cpu = Connector(Matrix.from_npa(x), context, context)
            np_lstm_rnn_cpu = NpLstmRnn(W_init, R_init, x_cpu)
            h, dL_dh = np_lstm_rnn_cpu.h.register_usage(context, context)
            np_lstm_rnn_cpu.fprop()
            Matrix.from_npa(random_matrix, 'float').copy(context, dL_dh)
            np_lstm_rnn_cpu.bprop()
            np_lstm_rnn_cpu.context.synchronize()
            dL_dW_cpu = np_lstm_rnn_cpu.dL_dW.to_host()
            dL_dR_cpu = np_lstm_rnn_cpu.dL_dR.to_host()
            dL_dx_cpu = np_lstm_rnn_cpu.dL_dx.to_host()

            r.append(np.allclose(dL_dW_gpu, dL_dW_cpu, rtol=1e-7, atol=1e-3))
            r.append(np.allclose(dL_dR_gpu, dL_dR_cpu, rtol=1e-7, atol=1e-3))
            r.append(np.allclose(dL_dx_gpu, dL_dx_cpu, rtol=1e-7, atol=1e-3))

        self.assertEqual(sum(r), self.N * 3)

    def test_finite_difference_x(self):
        quagga.processor_type = 'gpu'
        r = []
        n = 10

        for i in xrange(n):
            k = self.rng.random_integers(10)
            dim_x = self.rng.random_integers(50)
            dim_h = self.rng.random_integers(20)

            W_init = lambda: (np.random.rand(dim_h, dim_x) * 0.1).astype(np.float32)
            W_init.nrows, W_init.ncols = dim_h, dim_x
            R_init = lambda: (np.random.rand(dim_h, dim_h) * 0.1).astype(np.float32)
            R_init.nrows, R_init.ncols = dim_h, dim_h
            log_reg_init = lambda: (np.random.rand(1, dim_h) * 0.1).astype(np.float32)

            x = Connector(Matrix.from_npa(np.random.rand(dim_x, k), 'float'), b_usage_context=Context())
            true_labels = Connector(Matrix.from_npa(self.rng.choice(np.array([1, 0], dtype=np.float32), size=(1, k))))
            np_lstm_rnn = NpLstmRnn(W_init, R_init, x)
            log_reg = LogisticRegressionCe(log_reg_init, np_lstm_rnn.h, true_labels)

            x.fprop()
            true_labels.fprop()
            np_lstm_rnn.fprop()
            log_reg.fprop()
            log_reg.bprop()
            np_lstm_rnn.bprop()

            dL_dx = np_lstm_rnn.dL_dx.to_host()
            numerical_grad = np.zeros_like(dL_dx)
            cross_entropy = lambda l, p: -np.sum(l * np.log(p) + (1 - l) * np.log(1 - p))
            x_np = x.to_host()
            true_labels_np = true_labels.to_host()

            epsilon = 1e-2
            for i in xrange(x.nrows):
                for j in xrange(x.ncols):
                    x.__setitem__((i, j), x_np[i, j] + epsilon)
                    np_lstm_rnn.fprop()
                    log_reg.fprop()
                    probs = log_reg.probs.to_host()
                    plus_cost = cross_entropy(true_labels_np, probs)

                    x.__setitem__((i, j), x_np[i, j] - epsilon)
                    np_lstm_rnn.fprop()
                    log_reg.fprop()
                    probs = log_reg.probs.to_host()
                    minus_cost = cross_entropy(true_labels_np, probs)

                    numerical_grad[i, j] = (plus_cost - minus_cost) / (2 * epsilon)
                    x.__setitem__((i, j), x_np[i, j])

            r.append(np.allclose(dL_dx, numerical_grad, rtol=1e-7, atol=1e-4))

        self.assertEqual(sum(r), n)

    def test_finite_difference_w(self):
        quagga.processor_type = 'gpu'
        r = []
        n = 10

        for i in xrange(n):
            k = self.rng.random_integers(3)
            dim_x = self.rng.random_integers(50)
            dim_h = self.rng.random_integers(20)

            W_init = self.get_orthogonal_initializer(dim_h, dim_x)
            R_init = self.get_orthogonal_initializer(dim_h, dim_h)
            log_reg_init = lambda: (np.random.rand(1, dim_h) * 0.1).astype(np.float32)

            x = Connector(Matrix.from_npa(np.random.rand(dim_x, k), 'float'))
            true_labels = Connector(Matrix.from_npa(self.rng.choice(np.array([1, 0], dtype=np.float32), size=(1, k))))
            np_lstm_rnn = NpLstmRnn(W_init, R_init, x)
            log_reg = LogisticRegressionCe(log_reg_init, np_lstm_rnn.h, true_labels)

            x.fprop()
            true_labels.fprop()
            np_lstm_rnn.fprop()
            log_reg.fprop()
            log_reg.bprop()
            np_lstm_rnn.bprop()

            dL_d = {'W': np_lstm_rnn.dL_dW.to_host(),
                    'R': np_lstm_rnn.dL_dR.to_host()}
            cross_entropy = lambda l, p: -np.sum(l * np.log(p) + (1 - l) * np.log(1 - p))
            true_labels_np = true_labels.to_host()
            for variable in ['W', 'R']:
                dL_dvariable = dL_d[variable]
                numerical_grad = np.zeros_like(dL_d[variable])
                variable = getattr(np_lstm_rnn, variable)
                variable_np = variable.to_host()
                epsilon = 1e-2
                for i in xrange(variable.nrows):
                    for j in xrange(variable.ncols):
                        variable.__setitem__((i, j), variable_np[i, j] + epsilon)
                        np_lstm_rnn.fprop()
                        log_reg.fprop()
                        probs = log_reg.probs.to_host()
                        plus_cost = cross_entropy(true_labels_np, probs)

                        variable.__setitem__((i, j), variable_np[i, j] - epsilon)
                        np_lstm_rnn.fprop()
                        log_reg.fprop()
                        probs = log_reg.probs.to_host()
                        minus_cost = cross_entropy(true_labels_np, probs)

                        numerical_grad[i, j] = (plus_cost - minus_cost) / (2 * epsilon)
                        variable.__setitem__((i, j), variable_np[i, j])

                r.append(np.allclose(dL_dvariable, numerical_grad, rtol=1e-7, atol=1e-4))

        self.assertEqual(sum(r), 2 * n)