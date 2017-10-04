# -*- coding: utf-8 -*-
from __future__ import print_function

import logging
import sys
import threading
from time import sleep
import docker
from docker.errors import APIError
from requests import ConnectionError
from future.utils import raise_

__all__ = ['PythonDockerTestMixin', 'ConfigurationError', 'ContainerNotReady']

log = logging.getLogger(__name__)

DEFAULT_READY_TRIES = 10
DEFAULT_READY_SLEEP = 3


class ConfigurationError(Exception):
    pass


class ContainerNotReady(Exception):
    pass


class ContainerStartThread(threading.Thread):

    def __init__(
        self, image, ready_callback, ready_tries, ready_sleep,
        environment=None
    ):
        self.is_ready = threading.Event()
        self.error = None
        self.image = image
        self.ready_tries = ready_tries
        self.ready_sleep = ready_sleep
        self.ready_callback = ready_callback

        self.environment = environment

        super(ContainerStartThread, self).__init__()

    def run(self):
        log.debug("ContainerStartThread.run() executed")
        try:
            try:
                self.client = docker.Client(version='auto')
                self.client.ping()
            except ConnectionError as e:
                self.error = "Can't connect to docker. Is it installed/running?"
                raise

            # confirm that the image we want to run is present and pull if not
            try:
                self.client.inspect_image(self.image)
            except APIError as e:
                if '404' in str(e.message):
                    print("{} image not found; pulling...".format(self.image),
                          file=sys.stderr)
                    result = self.client.pull(self.image)
                    if 'error' in result:
                        raise ConfigurationError(result['error'])

            run_args = {'image': self.image, 'environment': self.environment}

            # create and start the container
            self.container = self.client.create_container(**run_args)
            self.client.start(self.container)
            self.container_data = self.client.inspect_container(self.container)

            if self.ready_callback is not None:
                # wait for the container to be "ready"
                print("Waiting for container to start...", file=sys.stderr)
                tries = self.ready_tries
                while tries > 0:
                    try:
                        print("Number of tries left: {}".format(tries),
                              file=sys.stderr)
                        self.ready_callback(self.container_data)
                        break
                    except ContainerNotReady:
                        tries -= 1
                        sleep(self.ready_sleep)

            self.is_ready.set()

        except Exception as e:
            self.exc_info = sys.exc_info()
            if self.error is None:
                self.error = e
            self.is_ready.set()

    def terminate(self):
        if hasattr(self, 'container'):
            self.client.stop(self.container)
            self.client.remove_container(self.container)


class PythonDockerTestMixin(object):

    @classmethod
    def setUpClass(cls):
        """
        Checks that image
        defined in cls.CONTAINER_IMAGE is present and pulls if not. Starts
        the container in a separate thread to allow for better cleanup if
        exceptions occur during test setup.
        """
        log.debug("custom setup class executed")

        if not hasattr(cls, 'CONTAINER_IMAGE'):
            raise ConfigurationError(
                "Test class missing CONTAINER_IMAGE attribute"
            )

        ready_tries = getattr(
            cls, 'CONTAINER_READY_TRIES', DEFAULT_READY_TRIES
        )
        ready_sleep = getattr(
            cls, 'CONTAINER_READY_SLEEP', DEFAULT_READY_SLEEP
        )
        ready_callback = getattr(cls, 'container_ready_callback')
        environment = getattr(cls, 'CONTAINER_ENVIRONMENT', None)

        cls.container_start_thread = ContainerStartThread(
            cls.CONTAINER_IMAGE,
            ready_callback,
            ready_tries,
            ready_sleep,
            environment
        )
        cls.container_start_thread.daemon = True
        cls.container_start_thread.start()

        # wait for the container startup to complete
        cls.container_start_thread.is_ready.wait()
        if cls.container_start_thread.error:
            exc_info = cls.container_start_thread.exc_info
            # Clean up behind ourselves,
            # since tearDownClass won't get called in case of errors.
            cls._tearDownClassInternal()
            raise raise_(exc_info[1], None, exc_info[2])

        cls.container_data = cls.container_start_thread.container_data

        super(PythonDockerTestMixin, cls).setUpClass()

    @classmethod
    def _tearDownClassInternal(cls):
        if hasattr(cls, 'container_start_thread'):
            cls.container_start_thread.terminate()
            cls.container_start_thread.join()
            delattr(cls, 'container_start_thread')

    @classmethod
    def tearDownClass(cls):
        super(PythonDockerTestMixin, cls).tearDownClass()
        cls._tearDownClassInternal()

    def setUp(self):
        self.container_ip = self.container_data['NetworkSettings']['IPAddress']
        self.docker_gateway_ip = self.container_data['NetworkSettings']['Gateway']
