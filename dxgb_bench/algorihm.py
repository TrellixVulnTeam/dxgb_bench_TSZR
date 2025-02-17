from typing import Optional, Union, Dict, Any
import argparse

from xgboost import dask as dxgb
import xgboost as xgb

from .utils import Timer, fprint, DC, ID
import tqdm

from distributed import Client
from time import time


EvalsLog = xgb.callback.TrainingCallback.EvalsLog


class Progress(xgb.callback.TrainingCallback):
    def __init__(self, n_rounds: int) -> None:
        super().__init__()
        self.n_rounds = n_rounds

    def before_training(self, model: xgb.Booster) -> xgb.Booster:
        self.start = time()
        self.pbar = tqdm.tqdm(total=self.n_rounds, unit="iter")
        return model

    def after_iteration(
        self, model: xgb.Booster, epoch: int, evals_log: EvalsLog
    ) -> bool:
        self.pbar.update(1)
        return False

    def after_training(self, model: xgb.Booster) -> xgb.Booster:
        self.end = time()
        self.pbar.close()
        return model


class XgbDaskBase:
    def __init__(self, parameters: dict, rounds: int, client: Client, eval: bool) -> None:
        self.parameters = parameters
        self.client = client
        self.num_boost_round = rounds
        self.name: str = "base"
        self.should_eval = eval

    def fit(self, X: DC, y: DC, weight: Optional[DC] = None) -> dict:
        with Timer(self.name, "DMatrix"):
            dtrain = dxgb.DaskDMatrix(self.client, data=X, label=y, weight=weight)

        if self.should_eval:
            callbacks = []
            evals = [(dtrain, "Train")]
        else:
            callbacks = [Progress(self.num_boost_round)]
            evals = []

        with Timer(self.name, "train"):
            output = dxgb.train(
                client=self.client,
                params=self.parameters,
                dtrain=dtrain,
                evals=evals,
                num_boost_round=self.num_boost_round,
                # callbacks=callbacks,
            )
            self.booster = output["booster"]
            return output["history"]

    def predict(self, X: DC) -> DC:
        with Timer(self.name, "predict"):
            predictions = dxgb.inplace_predict(self.client, self.booster, X)
            return predictions


class XgbDaskGpuHist(XgbDaskBase):
    def __init__(self, parameters: dict, rounds: int, client: Client, eval: bool) -> None:
        super().__init__(parameters, rounds, client, eval)
        self.name = "xgboost-dask-gpu-hist"
        self.parameters["tree_method"] = "gpu_hist"

    def fit(self, X: DC, y: DC, weight: Optional[DC] = None) -> EvalsLog:
        with xgb.config_context(verbosity=1):
            with Timer(self.name, "DaskDeviceQuantileDMatrix"):
                dtrain = dxgb.DaskDeviceQuantileDMatrix(
                    self.client, data=X, label=y, weight=weight
                )

            if self.should_eval:
                callbacks = []
                evals = [(dtrain, "Train")]
            else:
                callbacks = [Progress(self.num_boost_round)]
                evals = []

            with Timer(self.name, "train"):
                output = dxgb.train(
                    client=self.client,
                    params=self.parameters,
                    dtrain=dtrain,
                    evals=evals,
                    num_boost_round=self.num_boost_round,
                    # callbacks=callbacks,
                )
                self.booster = output["booster"]
                return output["history"]


class XgbDaskCpuHist(XgbDaskBase):
    def __init__(self, parameters: dict, rounds: int, client: Client, eval: bool) -> None:
        super().__init__(parameters, rounds, client, eval)
        self.name = "xgboost-dask-cpu-hist"
        self.parameters["tree_method"] = "hist"


class XgbDaskCpuApprox(XgbDaskBase):
    def __init__(self, parameters: dict, rounds: int, client: Client, eval: bool) -> None:
        super().__init__(parameters, rounds, client, eval)
        self.name = "xgboost-dask-cpu-approx"
        self.parameters["tree_method"] = "approx"


class XgbBase:
    def __init__(self, name: str, parameters: dict, rounds: int, eval: bool):
        self.name = name
        self.parameters = parameters
        self.num_boost_round = rounds
        self.should_eval = eval

    def fit(self, X: ID, y: ID, weight: Optional[ID] = None) -> EvalsLog:
        with xgb.config_context(verbosity=1):
            n_threads = self.parameters.get("nthread", 1)
            with Timer(self.name, "DMatrix"):
                dtrain = xgb.DMatrix(data=X, label=y, weight=weight, nthread=n_threads)

            if self.should_eval:
                evals = [(dtrain, "Train")]
                callbacks = []
            else:
                evals = ()
                callbacks = [Progress(self.num_boost_round)]

            with Timer(self.name, "train"):
                evals_result: EvalsLog = {}
                output = xgb.train(
                    params=self.parameters,
                    dtrain=dtrain,
                    evals=evals,
                    evals_result=evals_result,
                    num_boost_round=self.num_boost_round,
                    # callbacks=callbacks,
                )
                self.booster = output
                return evals_result

    def predict(self, X: ID) -> ID:
        return self.booster.inplace_predict(X)


class XgbCpuHist(XgbBase):
    def __init__(self, parameters: dict, rounds: int, eval: bool) -> None:
        self.parameters = parameters
        parameters["tree_method"] = "hist"
        super().__init__("xgboost-cpu-hist", parameters, rounds)


class XgbCpuApprox(XgbBase):
    def __init__(self, parameters: dict, rounds: int, eval: bool) -> None:
        parameters["tree_method"] = "approx"
        super().__init__("xgboost-cpu-approx", parameters, rounds)


class XgbGpuHist(XgbBase):
    def __init__(self, parameters: dict, rounds: int, eval: bool) -> None:
        parameters["tree_method"] = "gpu_hist"
        super().__init__("xgboost-gpu-hist", parameters, rounds, eval)

    def fit(self, X: ID, y: ID, weight: Optional[ID] = None) -> EvalsLog:
        with xgb.config_context(verbosity=1):
            n_threads = self.parameters.get("nthread", 1)
            with Timer(self.name, "DeviceQuantileDMatrix") as timer:
                try:
                    dtrain = xgb.DeviceQuantileDMatrix(
                        data=X, label=y, weight=weight, nthread=n_threads
                    )
                except TypeError:
                    dtrain = xgb.DMatrix(
                        data=X, label=y, weight=weight, nthread=n_threads
                    )
                    timer.proc = "DMatrix"

            if self.should_eval:
                evals = [(dtrain, "Train")]
                callbacks = []
            else:
                evals = ()
                callbacks = [Progress(self.num_boost_round)]

            with Timer(self.name, "train"):
                evals_result: EvalsLog = {}
                output = xgb.train(
                    params=self.parameters,
                    dtrain=dtrain,
                    evals=evals,
                    evals_result=evals_result,
                    num_boost_round=self.num_boost_round,
                    # callbacks=callbacks,
                )
                self.booster = output
                return evals_result


def factory(
    name: str,
    task: str,
    client: Optional[Client],
    args: argparse.Namespace,
    extra_args: Dict[str, Any]
) -> Union[XgbBase, XgbDaskBase]:
    parameters = {
        "max_depth": args.max_depth,
        "grow_policy": args.policy,
        "single_precision_histogram": args.f32_hist,
        "objective": task,
        "subsample": args.subsample,
        "colsample_bynode": args.colsample_bynode,
    }
    parameters.update(extra_args)

    if args.backend.find("dask") == -1:
        parameters["nthread"] = args.cpus

    print("parameters:", parameters)
    should_eval = args.eval == 1

    if args.backend.find("dask") != -1:
        if name == "xgboost-gpu-hist":
            return XgbDaskGpuHist(parameters, args.rounds, client, should_eval)
        elif name == "xgboost-cpu-approx":
            return XgbDaskCpuApprox(parameters, args.rounds, client, should_eval)
        elif name == "xgboost-cpu-hist":
            return XgbDaskCpuHist(parameters, args.rounds, client, should_eval)
    else:
        if name == "xgboost-gpu-hist":
            return XgbGpuHist(parameters, args.rounds, should_eval)
        elif name == "xgboost-cpu-hist":
            return XgbCpuHist(parameters, args.rounds, should_eval)
        elif name == "xgboost-cpu-approx":
            return XgbCpuApprox(parameters, args.rounds, should_eval)

    raise ValueError(
        "Unknown algorithm: ",
        name,
        " expecting one of the: {",
        "xgboost-gpu-hist",
        "xgboost-cpu-approx",
        "xgboost-cpu-hist",
        "}",
    )
