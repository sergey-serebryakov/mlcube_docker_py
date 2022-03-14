# MLCube docker runner with python `docker` library.

This is a PoC implementation of how to run [MLCubes](https://github.com/mlcommons/mlcube) with `docker` library. 
Existing implementation relies on invoking [shell commands](https://github.com/mlcommons/mlcube/blob/master/runners/mlcube_docker/mlcube_docker/docker_run.py). 
Idea is to start using [python library](https://github.com/docker/docker-py) instead.

## Prerequisites
Install docker. This code was tested on a machine with Windows OS.

## How to run
- Clone MLCube [examples](https://github.com/mlcommons/mlcube_examples).
- Create python environment and run `pip install -r requirements.txt`
- Set environment variables
  - Mandatory: `mlcube_examples` (path to the cloned repository).
  - Optional: `http_proxy`, `https_proxy`.
- Run [main.py](./main.py)

## Questions to answer
- What is the right way to print the output of a running container while it is running? Current implementation seems
  to be printing results at the end, once container stops.