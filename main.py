import argparse
import psutil
import os
import sys

# import dask_ml.metrics as dm
from dask.distributed import Client, LocalCluster, wait
from dask_cuda import LocalCUDACluster

from dxgb_bench.datasets import factory as data_factory
from dxgb_bench.utils import Timer, fprint, TemporaryDirectory
from dxgb_bench import algorihm

import dask
import pandas
import distributed
import cudf
import dask_cudf
import dask_cuda
import xgboost
import cupy

import json


def packages_version():
    packages = {
        'dask': dask.__version__,
        'pandas': pandas.__version__,
        'distributed': distributed.__version__,
        'cudf': cudf.__version__,
        'dask_cudf': dask_cudf.__version__,
        'dask_cuda': dask_cuda.__version__,
        'xgboost': xgboost.__version__,
        'cupy': cupy.__version__
    }
    return packages


def print_version():
    fprint('Package version:')
    packages = packages_version()
    for name, version in packages.items():
        fprint('- ' + name + ':', version)
    fprint()


def distributed_benchmark(args):
    def cluster_type(*user_args, **kwargs):
        if args.device == 'CPU':
            return LocalCluster(*user_args, **kwargs)
        else:
            assert args.gpus <= dask_cuda.utils.get_n_gpus()
            return LocalCUDACluster(*user_args, n_workers=args.gpus, **kwargs)

    def run_benchmark(client):
        (X, y, w), task = data_factory(args.data, args)
        with Timer(args.backend, 'Wait'):
            X = X.persist()
            y = y.persist()
            wait(X)
            wait(y)
        algo = algorihm.factory(args.algo, task, client, args)
        algo.fit(X, y, w)
        predictions = algo.predict(X).map_blocks(cupy.asarray)
        # https://github.com/rapidsai/cudf/issues/3671
        # metric = dm.mean_squared_error(y.values, predictions)
        # timer = Timer.global_timer()
        # timer[args.algo]['mse'] = metric

    with TemporaryDirectory(args.temporary_directory):
        # race condition for creating directory.
        # dask.config.set({'temporary_directory': args.temporary_directory})
        if args.scheduler is not None:
            with Client(scheduler_file=args.scheduler) as client:
                run_benchmark(client)
        else:
            with cluster_type(threads_per_worker=args.cpus) as cluster:
                print('dashboard link:', cluster.dashboard_link)
                with Client(cluster) as client:
                    run_benchmark(client)


def single_node_benchmark(args):
    (X, y, w), task = data_factory(args.data, args)
    assert args.backend == 'cudf' or args.backend == 'pandas'
    algo = algorihm.factory(args.algo, task, None, args)
    algo.fit(X, y, w)
    raise NotImplementedError()


def main(args):
    print_version()
    if not os.path.exists(args.temporary_directory):
        os.mkdir(args.temporary_directory)

    if args.distributed:
        distributed_benchmark(args)
    else:
        single_node_benchmark(args)

    if not os.path.exists(args.output_directory):
        os.mkdir(args.output_directory)

    # Don't override the previous result.
    i = 0
    while True:
        f = args.algo + '-rounds:' + \
            str(args.rounds) + '-data:' + args.data + '-' + str(i) + '.json'
        path = os.path.join(args.output_directory, f)
        if os.path.exists(path):
            i += 1
            continue
        with open(path, 'w') as fd:
            timer = Timer.global_timer()
            timer['packages'] = packages_version()
            timer['args'] = args.__dict__
            json.dump(timer, fd, indent=2)
            break


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Arguments for benchmarking with XGBoost dask.')
    parser.add_argument('--local-directory',
                        type=str,
                        help='Local directory for storing the dataset.',
                        default='dxgb_bench_workspace')
    parser.add_argument('--temporary-directory',
                        type=str,
                        help='Temporary directory used for dask.',
                        default='dask_workspace')
    parser.add_argument('--output-directory',
                        type=str,
                        help='Directory storing benchmark results.',
                        default='benchmark_outputs')
    parser.add_argument(
        '--scheduler',
        type=str,
        help='Scheduler address.  Use local cluster by default.',
        default=None)
    parser.add_argument('--device',
                        type=str,
                        help='CPU or GPU',
                        default='GPU')
    parser.add_argument(
        '--cpus',
        type=int,
        help='Number of CPUs, used for setting number of threads.',
        default=psutil.cpu_count(logical=False))
    parser.add_argument('--gpus',
                        type=int,
                        help='Number of GPUs.  One worker for each GPU.',
                        default=dask_cuda.utils.get_n_gpus())
    parser.add_argument('--algo',
                        type=str,
                        help='Used algorithm',
                        default='xgboost-dask-gpu-hist')
    parser.add_argument('--rounds',
                        type=int,
                        default=100,
                        help='Number of boosting rounds.')
    parser.add_argument('--data',
                        type=str,
                        help='Name of dataset.',
                        required=True)
    parser.add_argument('--backend',
                        type=str,
                        help='Data loading backend.',
                        default='dask_cudf')
    parser.add_argument('--distributed',
                        type=bool,
                        default=True,
                        help='Run on distributed environment or not.')
    args = parser.parse_args()
    try:
        main(args)
    except Exception as e:
        fprint(e)
        sys.exit(1)
