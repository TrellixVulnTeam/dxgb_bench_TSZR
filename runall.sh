run_large() {
    for data in {"mortgage", "taxi"}
    do
	python main.py --data=${data} --gpus=2
	python main.py --data=${data} --gpus=4
	python main.py --data=${data} --gpus=8
    done
}

run_small() {
    for data in {"higgs", "year"}
    do
	python main.py --data=${data} --gpus=1
	python main.py --data=${data} --gpus=2
	python main.py --data=${data} --gpus=4
    done
}

for i in {0..3}
do
    run_large
    run_small
done
