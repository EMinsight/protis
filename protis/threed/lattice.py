#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: Benjamin Vial
# This file is part of protis
# License: GPLv3
# See the documentation at protis.gitlab.io

__all__ = ["Lattice"]

from math import pi

from nannos.geometry import *

from .. import backend as bk
from .. import get_backend
from ..utils import is_scalar


class Lattice:
    """A lattice object defining the unit cell.

    Parameters
    ----------
    basis_vectors : tuple
        The lattice vectors :math:`((u1_x,u1_y,u1_z),(u2_x,u2_y,u2_z),(u3_x,u3_y,u3_z))`.

    discretization : int or tuple of length 3
        Spatial discretization of the lattice. If given an integer N, the
        discretization will be (N, N, N).

    truncation : str
        The truncation method, available values are "spherical" and "parallelogrammic" (the default is "spherical").

    harmonics_array : array of shape (3, nh)
        Array of harmonics. If specified, this is used instead of harmonics generated by
        the lattice object and nh is deduced from it.
    """

    def __init__(
        self,
        basis_vectors,
        discretization=2**8,
        truncation="parallelogrammic",
        harmonics_array=None,
    ):
        if is_scalar(discretization):
            discretization = [discretization, discretization]
        else:
            discretization = list(discretization)

        if truncation not in ["spherical", "parallelogrammic"]:
            raise ValueError(
                f"Unknown truncation method '{truncation}', please choose between 'spherical' and 'parallelogrammic'."
            )

        self.truncation = truncation
        self.basis_vectors = basis_vectors
        self.discretization = tuple(discretization)

        self.harmonics_array = harmonics_array

    @property
    def volume(self):
        v = self.basis_vectors
        return bk.linalg.norm(bk.cross(v[0], v[1]) @ v[2])

    @property
    def matrix(self):
        """Basis matrix.

        Returns
        -------
        array like
            Matrix containing the lattice vectors (L1,L2,L3).

        """
        return bk.array(self.basis_vectors, dtype=bk.float64).T

    @property
    def reciprocal(self):
        """Reciprocal matrix.

        Returns
        -------
        array like
            Matrix containing the lattice vectors (K1,K2) in reciprocal space.

        """
        return 2 * pi * bk.linalg.inv(self.matrix).T

    def get_harmonics(self, nh):
        """Get the harmonics with a given truncation method.

        Parameters
        ----------
        nh : int
            Number of harmonics.

        Returns
        -------
        G : list of tuple of integers of length 3
            Harmonics (i1, i2, i3).
        nh : int
            The number of harmonics after truncation.

        """

        if self.harmonics_array is not None:
            nh = bk.shape(self.harmonics_array)[1]
            return self.harmonics_array, nh
        if int(nh) != nh:
            raise ValueError("nh must be integer.")
        if self.truncation == "spherical":
            return _spherical_truncation(nh, self.reciprocal)
        else:
            return _parallelogramic_truncation(nh, self.reciprocal)

    @property
    def unit_grid(self):
        """Unit grid in cartesian coordinates.

        Returns
        -------
        array like
            The unit grid of size equal to the attribute `discretization`.

        """
        Nx, Ny, Nz = self.discretization
        x0 = bk.array(bk.linspace(0, 1.0, Nx))
        y0 = bk.array(bk.linspace(0, 1.0, Ny))
        z0 = bk.array(bk.linspace(0, 1.0, Nz))
        x_, y_, z_ = bk.meshgrid(x0, y0, z0, indexing="ij")
        return bk.stack([x_, y_, z_])

    @property
    def grid(self):
        """Grid in lattice vectors basis.

        Returns
        -------
        array like
            The grid of size equal to the attribute `discretization`.

        """
        return self.transform(self.unit_grid)

    def transform(self, grid):
        """Transform from cartesian to lattice coordinates.

        Parameters
        ----------
        grid : tuple of array like
            Input grid, typically obtained by meshgrid.

        Returns
        -------
        array like
            Transformed grid in lattice vectors basis.

        """
        if get_backend() == "torch":
            return bk.tensordot(self.matrix, grid.double(), dims=([2], [1], [0]))
        else:
            return bk.tensordot(self.matrix, grid, axes=(2, 1, 0))

    def ones(self):
        """Return a new array filled with ones.

        Returns
        -------
        array like
            A uniform complex 3D array with shape ``self.discretization``.

        """
        return bk.ones(self.discretization, dtype=bk.complex128)

    def zeros(self):
        """Return a new array filled with zeros.

        Returns
        -------
        array like
            A uniform complex 3D array with shape ``self.discretization``.

        """
        return bk.zeros(self.discretization, dtype=bk.complex128)

    def constant(self, value):
        """Return a new array filled with value.

        Returns
        -------
        array like
            A uniform complex 3D array with shape ``self.discretization``.

        """
        return self.ones() * value

    def geometry_mask(self, geom):
        """Return a geametry boolean mask discretized on the lattice grid.

        Parameters
        ----------
        geom : Shapely object
            The geometry.

        Returns
        -------
        array of bool
            The shape mask.

        """
        return geometry_mask(geom, self, *self.discretization)

    def polygon(self, vertices):
        return polygon(vertices, self, *self.discretization)

    def circle(self, center, radius):
        return circle(center, radius, self, *self.discretization)

    def ellipse(self, center, radii, rotate=0):
        return ellipse(center, radii, self, *self.discretization, rotate=rotate)

    def square(self, center, width, rotate=0):
        return square(center, width, self, *self.discretization, rotate=rotate)

    def rectangle(self, center, widths, rotate=0):
        return rectangle(center, widths, self, *self.discretization, rotate=rotate)

    def stripe(self, center, width):
        return abs(self.grid[0] - center) <= width / 2


def _parallelogramic_truncation(nh, Lk):
    ###### para
    u = bk.array([bk.linalg.norm(value) for value in Lk])

    NGroot = int((nh) ** (1 / 3))
    if NGroot % 2 == 0:
        NGroot -= 1

    M = NGroot // 2

    xG = bk.array(bk.arange(-M, NGroot - M))
    # xG = bk.array(bk.arange(-NGroot, NGroot-1))
    G = bk.meshgrid(xG, xG, xG, indexing="ij")
    G = [g.flatten() for g in G]

    Gl2 = 0

    for i in range(-1, 2):
        udot = bk.dot(Lk[i], Lk[i + 1])
        Gl2 += (
            G[i] ** 2 * u[i] ** 2
            + G[i + 1] ** 2 * u[i + 1] ** 2
            + 2 * G[i] * G[i + 1] * udot
        )

    jsort = bk.argsort(Gl2)
    Gsorted = [g[jsort] for g in G]

    nh = NGroot**3

    G = bk.vstack(Gsorted)[:, :nh]

    return G, nh


def _spherical_truncation(nh, Lk):
    raise NotImplementedError
    # u = bk.array([bk.linalg.norm(value) for value in Lk])
    # udot = bk.dot(*Lk)
    # ucross = bk.array(Lk[0][0] * Lk[1][1] - Lk[0][1] * Lk[1][0])

    # circ_area = nh * bk.abs(ucross)
    # circ_radius = bk.sqrt(circ_area / pi) + u[0] + u[1]

    # _int = int if get_backend() == "torch" else bk.int32

    # u_extent = bk.array(
    #     [
    #         1 + _int(circ_radius / (q * bk.sqrt(1.0 - udot**2 / (u[0] * u[1]) ** 2)))
    #         for q in u
    #     ]
    # )
    # xG, yG = [bk.array(bk.arange(-q, q + 1)) for q in u_extent]
    # G = bk.meshgrid(xG, yG, indexing="ij")
    # G = [g.flatten() for g in G]

    # Gl2 = bk.array(
    #     G[0] ** 2 * u[0] ** 2 + G[1] ** 2 * u[0] ** 2 + 2 * G[0] * G[1] * udot
    # )
    # jsort = bk.argsort(Gl2)
    # Gsorted = [g[jsort] for g in G]
    # Gl2 = Gl2[jsort]

    # nGtmp = (2 * u_extent[0] + 1) * (2 * u_extent[1] + 1)
    # if nh < nGtmp:
    #     nGtmp = nh

    # tol = 1e-10 * max(u[0] ** 2, u[1] ** 2)
    # for i in bk.arange(nGtmp - 1, -1, -1):
    #     if bk.abs(Gl2[i] - Gl2[i - 1]) > tol:
    #         break
    # nh = i

    # G = bk.vstack(Gsorted)[:, :nh]

    # return G, nh
