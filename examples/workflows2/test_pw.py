#!/usr/bin/env runaiida
# -*- coding: utf-8 -*-

__copyright__ = u"Copyright (c), This file is part of the AiiDA platform. For further information please visit http://www.aiida.net/.. All rights reserved."
__license__ = "MIT license, see LICENSE.txt file"
__version__ = "0.6.0"
__authors__ = "The AiiDA team."

from aiida.backends.utils import load_dbenv, is_dbenv_loaded

if not is_dbenv_loaded():
    load_dbenv()

import sys
import os
from aiida.common.example_helpers import test_and_get_code
from aiida.orm import DataFactory
from aiida.common.exceptions import NotExistent
from aiida.workflows2.execution_engine import execution_engine
from aiida.orm.calculation.job.quantumespresso.pw import PwCalculation
from aiida.workflows2.legacy.job_calculation import JobCalculation
import threading


def keep_ticking():
    execution_engine.tick()
    threading.Timer(10, keep_ticking()).start()

# If set to True, will ask AiiDA to run in serial mode (i.e., AiiDA will not
# invoke the mpirun command in the submission script)
run_in_serial_mode = False

################################################################

UpfData = DataFactory('upf')
ParameterData = DataFactory('parameter')
KpointsData = DataFactory('array.kpoints')
StructureData = DataFactory('structure')
try:
    dontsend = sys.argv[1]
    if dontsend == "--dont-send":
        submit_test = True
    elif dontsend == "--send":
        submit_test = False
    else:
        raise IndexError
except IndexError:
    print >> sys.stderr, ("The first parameter can only be either "
                          "--send or --dont-send")
    sys.exit(1)

try:
    codename = sys.argv[2]
except IndexError:
    codename = None

# If True, load the pseudos from the family specified below
# Otherwise, use static files provided
auto_pseudos = False

queue = None
# queue = "Q_aries_free"
settings = None
#####

alat = 4.  # angstrom
cell = [[alat, 0., 0., ],
        [0., alat, 0., ],
        [0., 0., alat, ],
        ]

# BaTiO3 cubic structure
s = StructureData(cell=cell)
s.append_atom(position=(0., 0., 0.), symbols=['Ba'])
s.append_atom(position=(alat / 2., alat / 2., alat / 2.), symbols=['Ti'])
s.append_atom(position=(alat / 2., alat / 2., 0.), symbols=['O'])
s.append_atom(position=(alat / 2., 0., alat / 2.), symbols=['O'])
s.append_atom(position=(0., alat / 2., alat / 2.), symbols=['O'])

elements = list(s.get_symbols_set())

if auto_pseudos:
    valid_pseudo_groups = UpfData.get_upf_groups(filter_elements=elements)

    try:
        pseudo_family = sys.argv[3]
    except IndexError:
        print >> sys.stderr, "Error, auto_pseudos set to True. You therefore need to pass as second parameter"
        print >> sys.stderr, "the pseudo family name."
        print >> sys.stderr, "Valid UPF families are:"
        print >> sys.stderr, "\n".join("* {}".format(i.name) for i in valid_pseudo_groups)
        sys.exit(1)

    try:
        UpfData.get_upf_group(pseudo_family)
    except NotExistent:
        print >> sys.stderr, "auto_pseudos is set to True and pseudo_family='{}',".format(pseudo_family)
        print >> sys.stderr, "but no group with such a name found in the DB."
        print >> sys.stderr, "Valid UPF groups are:"
        print >> sys.stderr, ",".join(i.name for i in valid_pseudo_groups)
        sys.exit(1)

parameters = ParameterData(dict={
    'CONTROL': {
        'calculation': 'scf',
        'restart_mode': 'from_scratch',
        'wf_collect': True,
        'tstress': True,
        'tprnfor': True,
    },
    'SYSTEM': {
        'ecutwfc': 40.,
        'ecutrho': 320.,
    },
    'ELECTRONS': {
        'conv_thr': 1.e-10,
    }})

kpoints = KpointsData()

# method gamma only
# settings = ParameterData(dict={'gamma_only':True})
# kpoints.set_kpoints_mesh([1,1,1])

# method list
# import numpy
# kpoints.set_kpoints([[i,i,0] for i in numpy.linspace(0,1,10)],
#                    weights = [1. for i in range(10)])

# method mesh
kpoints_mesh = 2
kpoints.set_kpoints_mesh([kpoints_mesh, kpoints_mesh, kpoints_mesh])

# to retrieve the bands
# (the object settings is optional)
settings_dict = {'also_bands': True}
settings = ParameterData(dict=settings_dict)

## For remote codes, it is not necessary to manually set the computer,
## since it is set automatically by new_calc
# computer = code.get_remote_computer()
# calc = code.new_calc(computer=computer)

# calc = code.new_calc()
job_calc = JobCalculation.build(PwCalculation).create()

# calc.label = "Test QE pw.x"
# calc.description = "Test calculation with the Quantum ESPRESSO pw.x code"
job_calc.set_max_wallclock_seconds(30 * 60)  # 30 min
# Valid only for Slurm and PBS (using default values for the
# number_cpus_per_machine), change for SGE-like schedulers
job_calc.set_resources({"num_machines": 1})
# if run_in_serial_mode:
#    calc.set_withmpi(False)
# Otherwise, to specify a given # of cpus per machine, uncomment the following:
job_calc.set_resources({"num_machines": 1, "num_mpiprocs_per_machine": 8})
job_calc.set_custom_scheduler_commands("#SBATCH --account=ch3")

if queue is not None:
    job_calc.set_queue_name(queue)

inputs = {
    'structure': s,
    'parameters': parameters,
    'kpoints': kpoints,
    'code': test_and_get_code(codename, expected_code_type='quantumespresso.pw'),
}
if settings is not None:
    inputs['settings'] = settings

# if auto_pseudos:
#     try:
#         calc.use_pseudos_from_family(pseudo_family)
#         print "Pseudos successfully loaded from family {}".format(pseudo_family)
#     except NotExistent:
#         print ("Pseudo or pseudo family not found. You may want to load the "
#                "pseudo family, or set auto_pseudos to False.")
#         raise
# else:
    raw_pseudos = [
        ("Ba.pbesol-spn-rrkjus_psl.0.2.3-tot-pslib030.UPF", 'Ba', 'pbesol'),
        ("Ti.pbesol-spn-rrkjus_psl.0.2.3-tot-pslib030.UPF", 'Ti', 'pbesol'),
        ("O.pbesol-n-rrkjus_psl.0.1-tested-pslib030.UPF", 'O', 'pbesol')]

    pseudos_to_use = {}
    for fname, elem, pot_type in raw_pseudos:
        absname = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                                "..", "submission",
                                                "data", fname))
        pseudo, created = UpfData.get_or_create(absname, use_first=True)
        if created:
            print "Created the pseudo for {}".format(elem)
        else:
            print "Using the pseudo for {} from DB: {}".format(elem, pseudo.pk)
        pseudos_to_use[elem] = pseudo
    inputs['pseudo'] = pseudos_to_use

job_calc.run(inputs=inputs, daemon=False)
keep_ticking()

