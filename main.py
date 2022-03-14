import os
import re
import six
import logging
import itertools
import typing as t
from docker.models.images import Image
from docker.utils.json_stream import json_stream
from docker import (DockerClient, errors, from_env)

logger: t.Optional[logging.Logger] = None


class Docker(object):
    """ A thin wrapper around docker-py library """

    @staticmethod
    def to_str(image: Image) -> str:
        """ Return human-friendly description of a docker image.
        Args:
            image: Docker image description.
        Returns:
            Human-friendly description of the image.
        """
        return f"Image(id={image.id}, short_id={image.short_id}, tags={image.tags}, labels={image.labels})"

    def __init__(self, client: t.Optional[DockerClient] = None) -> None:
        self.client = client if client is not None else from_env()

    def pull(self, name: str) -> t.Optional[Image]:
        """ Pull image from a remote docker repository.
        Args:
             name: Image name
        Returns:
            Image description of the pulled image identified by the `name`.
        """
        try:
            pull_result: t.Union[Image, t.List[Image]] = self.client.images.pull(name)
            if isinstance(pull_result, list):
                if len(pull_result) != 1:
                    logger.error("Docker pull failed (type(pull_result)=list, len(pull_result)=%d).", len(pull_result))
                image = pull_result[0]
            else:
                image = pull_result
        except errors.ImageNotFound as err:
            logger.error("Docker pull failed (image name=%s)", name, exc_info=err)
            image = None
        return image

    def build(self, path: str, dockerfile: str, tag: str, buildargs: t.Optional[t.Dict] = None,
              **kwargs) -> t.Optional[Image]:
        """ Build docker image without providing any output on a console.
        Args:
            path: A file system path for the build context. Usually, it is a directory containing Dockerfile file.
            dockerfile: A path to Dockerfile relative to `context`. Must be in `context` or one of its sub-folders.
            tag: Name of this docker image.
            buildargs: A dictionary of build arguments. Useful to include http/https proxy variables.
            kwargs: Any other parameters accepted by `DockerClient.images.build` method.
        Returns:
            Image description of the built image.
        """
        try:
            image, result_stream = self.client.images.build(
                path=path, dockerfile=dockerfile, tag=tag, buildargs=buildargs, **kwargs
            )
            return image
        except errors.BuildError as err:
            logger.error("Docker build failed (did you provide HTTP/HTTPS proxy variables?).", exc_info=err)
        return None

    def build_with_output(self, path: str, dockerfile: str, tag: str,
                          buildargs: t.Optional[t.Dict] = None, **kwargs) -> t.Optional[Image]:
        """ Build docker image and print build progress on a console, similar to `docker` command line tool.
        A copy-past implementation of the `self.client.images.build` method with print statements.
        Args:
            path: A file system path for the build context. Usually, it is a directory containing Dockerfile file.
            dockerfile: A path to Dockerfile relative to `context`. Must be in `context` or one of its sub-folders.
            tag: Name of this docker image.
            buildargs: A dictionary of build arguments. Useful to include http/https proxy variables.
            kwargs: Any other parameters accepted by `DockerClient.images.build` method.
        Returns:
            Image description of the built image.
        """
        resp = self.client.api.build(path=path, dockerfile=dockerfile, tag=tag, buildargs=buildargs, **kwargs)
        if isinstance(resp, six.string_types):
            return self.client.images.get(resp)
        last_event = None
        image_id = None
        result_stream, internal_stream = itertools.tee(json_stream(resp))
        for chunk in internal_stream:
            if 'error' in chunk:
                raise errors.BuildError(chunk['error'], result_stream)
            if 'stream' in chunk:
                print(chunk['stream'], flush=True, end='')
                match = re.search(
                    r'(^Successfully built |sha256:)([0-9a-f]+)$',
                    chunk['stream']
                )
                if match:
                    image_id = match.group(2)
            last_event = chunk
        if image_id:
            return self.client.images.get(image_id)
        raise errors.BuildError(last_event or 'Unknown', result_stream)

    def run(self, image: Image, command: str, volumes: t.Optional[t.Union[t.List, t.Dict]] = None,
            environment: t.Optional[t.Dict] = None, **kwargs) -> None:
        """ Run container.
        Args:
            image: Description of the image to run.
            command: Everything that usually goes at the very end of `docker run` command line tool. In the context of
                MLCube, this is usually MLCube task parameters.
            volumes: Description of volumes to mount.
            environment: Environment variables to set inside a container.
        Returns:
            Return status of this container run.
        """
        logger.info(f"Docker.run(image=%s, volumes=%s, environment=%s, "
                    f"command=%s)", image.tags[0], str(volumes), str(environment), command)
        # TODO: What is the right way to wait for container to finish and print logs at the same time?
        #       This implementation seems to print all log lines once container stops.
        output: t.Generator = self.client.containers.run(
            image=image.tags[0], command=command, detach =False, volumes=volumes, stream=True, remove=True,
            stderr=True, stdout=True, environment=environment, **kwargs
        )
        for line in output:
            print(line.decode('utf-8'), flush=True, end='')


def run_mnist(path: str, env_vars: t.Optional[t.Dict] = None) -> None:
    image_name: str = 'mlcommons/mnist:0.0.1'
    docker = Docker()

    try:
        image: Image = docker.client.images.get(image_name)
    except errors.ImageNotFound:
        image: Image = docker.build_with_output(path, 'Dockerfile', image_name, env_vars)

    docker.run(
        image,
        command='download --data-config=/storage/data.yaml  --log-dir=/storage --data-dir=/storage',
        volumes={f'{path}\\workspace': dict(bind='/storage')},
        environment=env_vars
    )
    docker.run(
        image,
        command='train --train-config=/storage/train.yaml  --log-dir=/storage --data-dir=/storage --model-dir=/storage',
        volumes={f'{path}\\workspace': dict(bind='/storage')},
        environment=env_vars
    )


def _get_env_variables() -> t.Dict:
    """ Return docker build and run args. """
    build_args = {}
    for name in ['http_proxy', 'https_proxy']:
        if name in os.environ:
            build_args[name] = os.environ[name]
    return build_args


def main():
    try:
        run_mnist(
            path=os.path.join(os.environ.get('mlcube_examples'), 'mnist'),
            env_vars=_get_env_variables()
        )
    except errors.ContainerError as err:
        print(f"Command {err.command} in image {err.image} returned non-zero exit status {err.exit_status}. "
              "Output:\n")
        print(str(err.stderr or '').replace(r'\n', '\n'))


if __name__ == '__main__':
    import logging.config
    LOGGING_CONFIG = {
        'version': 1,
        'disable_existing_loggers': False,
        'root': {'level': 'INFO', 'handlers' : ['console']},
        'handlers':{'console':{'class': 'logging.StreamHandler', 'level': 'INFO'}}
    }
    logging.config.dictConfig(LOGGING_CONFIG)
    logger = logging.getLogger(__name__)

    main()
