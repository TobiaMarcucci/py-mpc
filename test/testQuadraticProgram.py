import unittest
import numpy as np
import mpc.symbolic as sym
from mpc.mpc_tools import quadratic_program, DTLinearSystem
import pydrake.solvers.mathematicalprogram as mp


class TestQuadraticProgram(unittest.TestCase):
    def test_round_trip(self):

        np.random.seed(0)
        for i in range(20):
            x_goal = np.random.rand(3) * 20 - 10
            prog1 = mp.MathematicalProgram()
            x = prog1.NewContinuousVariables(3, "x")
            prog1.AddLinearConstraint(x[0] >= 1)
            prog1.AddLinearConstraint(x[0] <= 10)
            prog1.AddLinearConstraint(x[0] + 5 * x[1] <= 11)
            prog1.AddLinearConstraint(-x[1] + 5 * x[0] <= 5)
            prog1.AddLinearConstraint(x[2] == x[0] + -2 * x[1])
            prog1.AddQuadraticCost(np.sum(np.power(x - x_goal, 2)))
            prog1.Solve()
            xstar_prog1 = prog1.GetSolution(x)
            simple = sym.SimpleQuadraticProgram.from_mathematicalprogram(prog1)
            xstar_qp, cost = quadratic_program(simple.H, simple.f,
                                           simple.A, simple.b,
                                           simple.C, simple.d)
            self.assertTrue(np.allclose(xstar_prog1, xstar_qp.flatten(), atol=1e-7))

            prog2, x2, T = simple.to_mathematicalprogram()
            prog2.Solve()
            xstar_prog2 = prog2.GetSolution(x2)
            self.assertTrue(np.allclose(xstar_prog1, T.A.dot(xstar_prog2) + T.b))

    def test_substitution(self):
        np.random.seed(1)
        for i in range(20):
            x_goal = np.random.rand(2) * 10 - 5
            prog = mp.MathematicalProgram()
            x = prog.NewContinuousVariables(2, "x")
            prog.AddLinearConstraint(x[0] >= 1)
            prog.AddLinearConstraint(x[1] >= 1)
            prog.AddLinearConstraint(x[0] + x[1] <= np.random.randint(4, 10))
            prog.AddQuadraticCost(np.sum(np.power(x - x_goal, 2)))

            simple_x = sym.SimpleQuadraticProgram.from_mathematicalprogram(prog)
            # x = T y + u
            T = np.random.rand(2, 2) - 0.5
            u = np.random.rand(2) - 0.5
            simple_y = simple_x.affine_variable_substitution(T, u)

            ystar = simple_y.solve()
            xstar = simple_x.solve()

            self.assertTrue(np.allclose(ystar, xstar))

    def test_permutation(self):
        np.random.seed(2)
        for i in range(20):
            x_goal = np.random.rand(3) * 20 - 10
            prog = mp.MathematicalProgram()
            x = prog.NewContinuousVariables(3, "x")
            prog.AddLinearConstraint(x[0] >= 1)
            prog.AddLinearConstraint(x[0] <= 10)
            prog.AddLinearConstraint(x[0] + 5 * x[1] <= 11)
            prog.AddLinearConstraint(-x[1] + 5 * x[0] <= 5)
            prog.AddLinearConstraint(x[2] == x[0] + -2 * x[1])
            prog.AddQuadraticCost(np.sum(np.power(x - x_goal, 2)))

            order = np.arange(x.size)
            np.random.shuffle(order)

            simple_x = sym.SimpleQuadraticProgram.from_mathematicalprogram(prog)

            # y = P * x = x[order]
            P = sym.permutation_matrix(order)
            # x = P^-1 * y
            simple_y = simple_x.affine_variable_substitution(np.linalg.inv(P),
                                                             np.zeros(x.size))
            ystar = simple_y.solve()
            xstar = simple_x.solve()
            self.assertTrue(np.allclose(ystar, xstar))

            simple_z = simple_x.permute_variables(order)
            zstar = simple_z.solve()
            self.assertTrue(np.allclose(zstar, xstar))

    def test_elimination(self):
        m = 1.
        l = 1.
        g = 10.
        N = 5
        A = np.array([
            [0., 1.],
            [g/l, 0.]
        ])
        B = np.array([
            [0.],
            [1/(m*l**2.)]
        ])
        t_s = .1
        sys = DTLinearSystem.from_continuous(t_s, A, B)

        x_max = np.array([np.pi/6., np.pi/22. / (N*t_s)])
        x_min = -x_max
        u_max = np.array([m*g*l*np.pi/8.])
        u_min = -u_max

        Q = np.eye(A.shape[0])/100.
        R = np.eye(B.shape[1])
        dim = 2

        np.random.seed(3)
        for i in range(20):
            x_goal = np.random.rand(dim) * (x_max - x_min) + x_min
            prog = mp.MathematicalProgram()

            u = prog.NewContinuousVariables(1, N, "u")
            x = prog.NewContinuousVariables(2, N, "x")

            for j in range(N - 1):
                x_next = sys.A.dot(x[:, j]) + sys.B.dot(u[:, j])
                for i in range(dim):
                    prog.AddLinearConstraint(x[i, j + 1] == x_next[i])

            for j in range(N):
                for i in range(x.shape[0]):
                    prog.AddLinearConstraint(x[i, j] <= x_max[i])
                    prog.AddLinearConstraint(x[i, j] >= x_min[i])
                for i in range(u.shape[0]):
                    prog.AddLinearConstraint(u[i, j] <= u_max[i])
                    prog.AddLinearConstraint(u[i, j] >= u_min[i])

            for j in range(N):
                prog.AddQuadraticCost((x[:, j] - x_goal).dot(Q).dot(x[:, j] - x_goal))
                prog.AddQuadraticCost(u[:, j].T.dot(R).dot(u[:, j]))

            simple = sym.SimpleQuadraticProgram.from_mathematicalprogram(prog)
            simple_eliminated = simple.eliminate_equality_constrained_variables()

            self.assertEqual(simple_eliminated.C.shape[0], 0)
            self.assertEqual(simple_eliminated.d.shape[0], 0)
            self.assertTrue(np.allclose(simple.solve(), simple_eliminated.solve()))

    def test_mpc_order(self):
        m = 1.
        l = 1.
        g = 10.
        N = 5
        A = np.array([
            [0., 1.],
            [g/l, 0.]
        ])
        B = np.array([
            [0.],
            [1/(m*l**2.)]
        ])
        t_s = .1
        sys = DTLinearSystem.from_continuous(t_s, A, B)

        x_max = np.array([np.pi/6., np.pi/22. / (N*t_s)])
        x_min = -x_max
        u_max = np.array([m*g*l*np.pi/8.])
        u_min = -u_max

        Q = np.eye(A.shape[0])/100.
        R = np.eye(B.shape[1])
        dim = 2

        np.random.seed(3)
        for i in range(20):
            x_goal = np.random.rand(dim) * (x_max - x_min) + x_min
            prog = mp.MathematicalProgram()

            x = prog.NewContinuousVariables(2, N, "x")
            u = prog.NewContinuousVariables(1, N, "u")

            for j in range(N - 1):
                x_next = sys.A.dot(x[:, j]) + sys.B.dot(u[:, j])
                for i in range(dim):
                    prog.AddLinearConstraint(x[i, j + 1] == x_next[i])

            for j in range(N):
                for i in range(x.shape[0]):
                    prog.AddLinearConstraint(x[i, j] <= x_max[i])
                    prog.AddLinearConstraint(x[i, j] >= x_min[i])
                for i in range(u.shape[0]):
                    prog.AddLinearConstraint(u[i, j] <= u_max[i])
                    prog.AddLinearConstraint(u[i, j] >= u_min[i])

            for j in range(N):
                prog.AddQuadraticCost((x[:, j] - x_goal).dot(Q).dot(x[:, j] - x_goal))
                prog.AddQuadraticCost(u[:, j].T.dot(R).dot(u[:, j]))

            simple = sym.SimpleQuadraticProgram.from_mathematicalprogram(prog)
            order = sym.mpc_order(prog, u, x)
            simple_permuted = simple.permute_variables(order)
            self.assertTrue(np.allclose(simple.solve(), simple_permuted.solve()))

            simple_eliminated = simple_permuted.eliminate_equality_constrained_variables()
            self.assertTrue(np.allclose(simple.solve(), simple_eliminated.solve()))

    def test_recenter(self):
        np.random.seed(2)
        for i in range(20):
            x_goal = np.random.rand(3) * 20 - 10
            prog = mp.MathematicalProgram()
            x = prog.NewContinuousVariables(3, "x")
            prog.AddLinearConstraint(x[0] >= 1)
            prog.AddLinearConstraint(x[0] <= 10)
            prog.AddLinearConstraint(x[0] + 5 * x[1] <= 11)
            prog.AddLinearConstraint(-x[1] + 5 * x[0] <= 5)
            prog.AddLinearConstraint(x[2] == x[0] + -2 * x[1])
            prog.AddQuadraticCost(np.sum(np.power(x - x_goal, 2)))

            qp = sym.SimpleQuadraticProgram.from_mathematicalprogram(prog)
            recentered = qp.transform_goal_to_origin()
            self.assertFalse(np.allclose(qp.f, 0))
            self.assertTrue(np.allclose(recentered.f, 0))
            self.assertTrue(np.allclose(recentered.solve(), qp.solve(), atol=1e-7))

    def test_canonical_qp(self):
        m = 1.
        l = 1.
        g = 10.
        N = 4
        A = np.array([
            [0., 1.],
            [g/l, 0.]
        ])
        B = np.array([
            [0.],
            [1/(m*l**2.)]
        ])
        t_s = .1
        sys = DTLinearSystem.from_continuous(t_s, A, B)

        x_max = np.array([np.pi/6., np.pi/22. / (N*t_s)])
        x_min = -x_max
        u_max = np.array([m*g*l*np.pi/8.])
        u_min = -u_max

        Q = np.eye(A.shape[0])/100.
        R = np.eye(B.shape[1])
        dim = 2

        np.random.seed(3)
        for i in range(20):
            x_goal = np.random.rand(dim) * (x_max - x_min) + x_min
            x_start = np.array([0., 0.])
            prog = mp.MathematicalProgram()

            x = prog.NewContinuousVariables(2, N, "x")
            u = prog.NewContinuousVariables(1, N, "u")

            for j in range(N - 1):
                x_next = sys.A.dot(x[:, j]) + sys.B.dot(u[:, j])
                for i in range(dim):
                    prog.AddLinearConstraint(x[i, j + 1] == x_next[i])

            for j in range(N):
                for i in range(x.shape[0]):
                    prog.AddLinearConstraint(x[i, j] <= x_max[i])
                    prog.AddLinearConstraint(x[i, j] >= x_min[i])
                for i in range(u.shape[0]):
                    prog.AddLinearConstraint(u[i, j] <= u_max[i])
                    prog.AddLinearConstraint(u[i, j] >= u_min[i])

            for j in range(N):
                prog.AddQuadraticCost((x[:, j] - x_goal).dot(Q).dot(x[:, j] - x_goal))
                prog.AddQuadraticCost(u[:, j].T.dot(R).dot(u[:, j]))

            assert prog.Solve() == mp.SolutionResult.kSolutionFound
            qp = sym.SimpleQuadraticProgram.from_mathematicalprogram(prog)
            mpc_qp = sym.CanonicalMPCQP.from_mathematicalprogram(prog, u, x)
            self.assertTrue(np.allclose(qp.solve(), mpc_qp.solve(), atol=1e-7))

if __name__ == '__main__':
    unittest.main()
