from xgboost import dask as dxgb
import xgboost as xgb
from .utils import Timer, fprint


class XgbDaskBase:
    def __init__(self, parameters, rounds, client):
        self.parameters = parameters
        self.client = client
        self.num_boost_round = rounds

    def fit(self, X, y, weight=None):
        with Timer(self.name, 'DMatrix'):
            dtrain = dxgb.DaskDMatrix(
                self.client, data=X, label=y, weight=weight
            )
        with Timer(self.name, 'train'):
            output = dxgb.train(client=self.client,
                                params=self.parameters,
                                dtrain=dtrain,
                                evals=[(dtrain, "Train")],
                                num_boost_round=self.num_boost_round)
            self.output = output
            return output["history"]

    def predict(self, X):
        with Timer(self.name, "predict"):
            predictions = dxgb.inplace_predict(self.client, self.output, X)
            return predictions


class XgbDaskGpuHist(XgbDaskBase):
    def __init__(self, parameters, rounds, client):
        super().__init__(parameters, rounds, client)
        self.name = "xgboost-dask-gpu-hist"
        self.parameters["tree_method"] = "gpu_hist"

    def fit(self, X, y, weight=None):
        with xgb.config_context(verbosity=1):
            with Timer(self.name, "DaskDeviceQuantileDMatrix"):
                dtrain = dxgb.DaskDeviceQuantileDMatrix(
                    self.client, data=X, label=y, weight=weight
                )
            with Timer(self.name, "train"):
                output = dxgb.train(
                    client=self.client,
                    params=self.parameters,
                    dtrain=dtrain,
                    evals=[(dtrain, "Train")],
                    num_boost_round=self.num_boost_round,
                )
                self.output = output
                return output["history"]


class XgbDaskCpuHist(XgbDaskBase):
    def __init__(self, parameters, rounds, client):
        super().__init__(parameters, rounds, client)
        self.name = "xgboost-dask-cpu-hist"
        self.parameters["tree_method"] = "hist"


class XgbDaskCpuApprox(XgbDaskBase):
    def __init__(self, parameters, rounds, client):
        super().__init__(parameters, rounds, client)
        self.name = "xgboost-dask-cpu-approx"
        self.parameters["tree_method"] = "approx"


class XgbBase:
    def fit(self, X, y, weight=None):
        with xgb.config_context(verbosity=1):
            with Timer(self.name, "DMatrix"):
                dtrain = xgb.DMatrix(data=X, label=y, weight=weight)
            with Timer(self.name, "train"):
                evals_result = {}
                output = xgb.train(
                    params=self.parameters,
                    dtrain=dtrain,
                    evals=[(dtrain, "Train")],
                    evals_result=evals_result,
                    num_boost_round=self.num_boost_round,
                )
                self.output = output
                return evals_result

    def predict(self, X):
        return self.output.inplace_predict(X)


class XgbCpuHist(XgbBase):
    def __init__(self, parameters, rounds):
        self.name = "xgboost-cpu-hist"
        self.parameters = parameters
        self.num_boost_round = rounds
        self.parameters["tree_method"] = "hist"


class XgbCpuApprox(XgbBase):
    def __init__(self, parameters, rounds):
        self.name = "xgboost-cpu-approx"
        self.parameters = parameters
        self.num_boost_round = rounds
        self.parameters["tree_method"] = "approx"


class XgbGpuHist:
    def __init__(self, parameters, rounds):
        self.name = "xgboost-gpu-hist"
        self.parameters = parameters
        self.num_boost_round = rounds
        self.parameters["tree_method"] = "gpu_hist"

    def fit(self, X, y, weight=None):
        with xgb.config_context(verbosity=1):
            with Timer(self.name, "DeviceQuantileDMatrix"):
                dtrain = xgb.DeviceQuantileDMatrix(data=X, label=y, weight=weight)
            with Timer(self.name, "train"):
                evals_result = {}
                output = xgb.train(
                    params=self.parameters,
                    dtrain=dtrain,
                    evals=[(dtrain, "Train")],
                    evals_result=evals_result,
                    num_boost_round=self.num_boost_round,
                )
                self.output = output
                return evals_result


def factory(name, task, client, args):
    parameters = {
        'max_depth': args.max_depth,
        "grow_policy": args.policy,
        "single_precision_histogram": args.f32_hist,
        'objective': task,
    }
    if args.backend.find("dask") != -1:
        parameters["nthread"] = args.cpus

    print("parameters:", parameters)
    if args.backend.find("dask") != -1:
        if name == "xgboost-gpu-hist":
            return XgbDaskGpuHist(parameters, args.rounds, client)
        elif name == "xgboost-cpu-approx":
            return XgbDaskCpuApprox(parameters, args.rounds, client)
        elif name == "xgboost-cpu-hist":
            return XgbDaskCpuHist(parameters, args.rounds, client)
    else:
        if name == "xgboost-gpu-hist":
            return XgbGpuHist(parameters, args.rounds)
        elif name == "xgboost-cpu-hist":
            return XgbCpuHist(parameters, args.rounds)
        elif name == "xgboost-cpu-approx":
            return XgbCpuApprox(parameters, args.rounds)

    raise ValueError(
        "Unknown algorithm: ",
        name,
        " expecting one of the: {",
        "xgboost-gpu-hist",
        "xgboost-cpu-approx",
        "xgboost-cpu-hist",
        "}"
    )
