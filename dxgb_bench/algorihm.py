from xgboost import dask as dxgb
from .utils import Timer


class XgbDaskBase:
    def __init__(self, parameters, rounds, client):
        self.parameters = parameters
        self.client = client
        self.num_boost_round = rounds

    def fit(self, X, y, weight=None):
        with Timer(self.name, 'DMatrix'):
            dtrain = dxgb.DaskDMatrix(self.client,
                                      data=X,
                                      label=y,
                                      weight=weight)
        with Timer(self.name, 'train'):
            output = dxgb.train(client=self.client,
                                params=self.parameters,
                                dtrain=dtrain,
                                num_boost_round=self.num_boost_round)
            self.output = output
            return output

    def predict(self, X):
        dtest = dxgb.DaskDMatrix(self.client, X)
        with Timer(self.name, 'predict'):
            predictions = dxgb.predict(self.client, self.output,
                                       dtest)
            return predictions


class XgbDaskGpuHist(XgbDaskBase):
    def __init__(self, parameters, rounds, client):
        super().__init__(parameters, rounds, client)
        self.name = 'xgboost-dask-gpu-hist'
        self.parameters['tree_method'] = 'gpu_hist'


class XgbDaskCpuHist(XgbDaskBase):
    def __init__(self, parameters, rounds, client):
        super().__init__(parameters, rounds, client)
        self.name = 'xgboost-dask-cpu-hist'
        self.parameters['tree_method'] = 'hist'


class XgbDaskCpuApprox(XgbDaskBase):
    def __init__(self, parameters, rounds, client):
        super().__init__(parameters, rounds, client)
        self.name = 'xgboost-dask-cpu-approx'
        self.parameters['tree_method'] = 'approx'


class XgbSingleNodeBase:
    def __init__(self, parameters, rounds):
        self.parameters = parameters
        self.rounds = rounds


class XgbGpuHist(XgbSingleNodeBase):
    def __init__(self, parameters, rounds):
        super().__init__(parameters, rounds)
        self.name = 'xgboost-gpu-hist'
        self.parameters['tree_method'] = 'gpu_hist'


def factory(name, task, client, args):
    parameters = {
        'max_depth': 8,
        'nthread': args.cpus,
        'objective': task
    }
    if name == 'xgboost-dask-gpu-hist':
        return XgbDaskGpuHist(parameters, args.rounds, client)
    elif name == 'xgboost-dask-cpu-hist':
        return XgbDaskCpuHist(parameters, args.rounds, client)
    elif name == 'xgboost-dask-cpu-approx':
        return XgbDaskCpuApprox(parameters, args.rounds, client)
    # single node algorithms.
    elif name == 'xgboost-gpu-hist':
        return XgbGpuHist(parameters, args.rounds)
