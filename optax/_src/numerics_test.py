# Copyright 2019 DeepMind Technologies Limited. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for optax._src.numerics."""

import functools
import itertools
import re

from absl.testing import absltest
from absl.testing import parameterized

import chex
import jax
import jax.numpy as jnp
import numpy as np

from optax._src import numerics

_ALL_ORDS = [None, np.inf, -np.inf, 'fro', 'nuc', 0, 1, 2, -2, -2, -1.5, 1.5]

int32_array = lambda i: jnp.array(i, dtype=jnp.int32)
float32_array = lambda i: jnp.array(i, dtype=jnp.float32)


def _invalid_ord_axis_inputs(ord_axis_keepdims):
  ord_, axis = ord_axis_keepdims[0], ord_axis_keepdims[1]
  return any(((ord_ == 0 and axis is None),
              (isinstance(ord_, float) and axis is None),
              (isinstance(ord_, str) and axis is not None)))


class NumericsTest(chex.TestCase):

  @chex.all_variants
  def test_safe_int32_increments(self):
    inc_fn = self.variant(numerics.safe_int32_increment)
    # increment small numbers correctly.
    base = int32_array(3)
    incremented = inc_fn(base)
    np.testing.assert_array_equal(incremented, int32_array(4))
    # avoid overflow when incrementing maxint.
    base = int32_array(np.iinfo(np.int32).max)
    incremented = inc_fn(base)
    np.testing.assert_array_equal(incremented, base)

  @chex.all_variants
  @parameterized.parameters(
      itertools.filterfalse(
          _invalid_ord_axis_inputs,
          itertools.product(_ALL_ORDS, [None, 0, 1], [False, True])))
  def test_safe_norm(self, ord, axis, keepdims):  # pylint: disable=redefined-builtin
    dnorm_dx = self.variant(
        jax.jacfwd(
            functools.partial(
                numerics.safe_norm, ord=ord, axis=axis, keepdims=keepdims),
            argnums=0))
    # Test gradient is 0. in 0. when zero min norm is used.
    g = dnorm_dx(float32_array(jnp.zeros((3, 4))), float32_array(0.))
    np.testing.assert_array_equal(g, jnp.zeros_like(g))
    # Test gradient is 0. in 0. when non zero min norm is used.
    g = dnorm_dx(float32_array(jnp.zeros((3, 4))), float32_array(3.))
    np.testing.assert_array_equal(g, jnp.zeros_like(g))

  @chex.all_variants
  def test_safe_rms(self):
    drms_dx = self.variant(jax.grad(numerics.safe_root_mean_squares))
    # Test gradient is 0. in 0. when zero min rms is used.
    g = drms_dx(float32_array(0.), float32_array(0.))
    np.testing.assert_array_equal(g, jnp.zeros_like(g))
    # Test gradient is 0. in 0. when non zero min rms is used.
    g = drms_dx(float32_array(0.), float32_array(3.))
    np.testing.assert_array_equal(g, jnp.zeros_like(g))

  def test_complex_vs_real_abs_sqr(self):
    # Tests that JAX generates the same HLO from `numerics.abs_sq`,
    # `jnp.square(x)`, `x * x`,  and `x**2`.
    real_sq_fns = (lambda x: x**2, lambda x: x * x, jnp.square)

    def _get_hlo_repr(f, x):
      hlo_string = jax.xla_computation(f)(x).as_hlo_text()
      return re.sub('HloModule.*?\n', '',
                    re.sub('ENTRY.*?{', 'ENTRY XXXX', hlo_string))

    # Real arg (same HLO).
    for real_sq_fn in real_sq_fns:
      for real_x in (3, 3.0, np.array([4, 5.2])):
        self.assertEqual(
            _get_hlo_repr(real_sq_fn, real_x),
            _get_hlo_repr(numerics.abs_sq, real_x))

    # Complex arg (different HLOs).
    for real_sq_fn in real_sq_fns:
      for complex_x in (1j, 3. + 1j, np.array([4 + 1j, 5.2 + 1j])):
        self.assertNotEqual(
            _get_hlo_repr(real_sq_fn, complex_x),
            _get_hlo_repr(numerics.abs_sq, complex_x))


if __name__ == '__main__':
  absltest.main()
