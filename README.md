## python-docker-test

**What this is**: A unittest.TestCase mixin for executing functional/integration
tests against containerized services. You configure the type of docker container
you wish to run as part of your tests, and the mixin's `setUpClass()` method
handles starting the container, waiting for the container to be ready, and
storing the container's `inspect` response data as part of the TestCase instance.

**What this is not**: A tool for testing your python app inside a docker
container. There are other solutions/packages for that already.

I wanted a mechanism by which I could automate some functional tests involving
a python [LTI](http://developers.imsglobal.org/) app (Django) and an external service, Instructure's [Canvas LMS](https://github.com/instructure/canvas-lms). LTI
is a standard that allows external apps to be embedded within an LMS's website by
means of an iframe. This makes it very difficult to do functional tests in
isolation. So I created a docker image for spinning up a dev instance of Canvas
and also this TestCase mixin for the purposes of automating it's execution
during my tests. It's a pretty narrow use case, but the hope is that it can be
useful for other types of containers.

### Getting started

`pip install python-docker-test`

### Writing the test case class

To create a functional test that relies on a docker container you'll need to
include a few additions to to your TestCase subclass:

1. Insert `PythonDockerTestMixin` at the beginning of your TestCase inheiritance
chain. See [here](http://nedbatchelder.com/blog/201210/multiple_inheritance_is_hard.html) for why the position is important.

1. Define at least the `CONTAINER_IMAGE` class attribute to specify the docker
image you wish to run. If the specified image is not found in your local docker
instance it will be pulled from the public registry.

1. Optional but recommended, define a `container_ready_callback` class method.
This method will be called from the thread that handles running the container.
Within this method you should do things to confirm that whatever's running in
your container is ready to run whatever your tests are exercising. The method
should simply return if everything is all set, otherwise raise a
`python_docker_test.ContainerNotReady`. The method will be called with a
positional argument of a dict structure containing the result of docker-py's
[`inspect_container`](http://docker-py.readthedocs.org/en/latest/api/#inspect_container), so you can know things like the container's ip and gateway
address.

1. Optionally set the `CONTAINER_READY_TRIES` and `CONTAINER_READY_SLEEP` class
attributes to control how many times your `container_ready_callback` method is
called before giving up, and how long the thread will sleep between calls.

### Example


```python

    import unittest
    from python_docker_test import PythonDockerTestMixin

    class MyTests(PythonDockerTestMixin, unittest.TestCase):

        CONTAINER_IMAGE = 'foobar/my_image'
        CONTAINER_READY_TRIES = 3
        CONTAINER_READY_SLEEP = 10
        CONTAINER_ENVIRONMENT = {'MYSQL_ALLOW_EMPTY_PASSWORD': True}

        @classmethod
        def container_ready_callback(cls, container_data):
            try:
                # request to base url should redirect to login when ready
                container_ip = container_data['NetworkSettings']['IPAddress']
                resp = requests.head('http://{}:3000'.format(container_ip))
                assert resp.status_code == 302
                return
            except (requests.ConnectionError, AssertionError):
                raise ContainerNotReady()

        def test_something(self):
            # container should be running; test some stuff!
            ...       
```

### App <-> Container networking

If, like me, you need the service(s) in the container to communicate back to the
app under test there is an additional hurdle of making the app accessible from
within the container. The simplest approach that I found is to bind the app to
the container's gateway IP. By default, using docker's "bridge" networking mode,
the gateway address is `172.17.42.1`. So, assuming a Django app, prior to
executing the functional tests you'll need to start an instance of your app like
so:

`python manage.py runserver 172.17.42.1:8000`

You should then be able to access the app at that address from within the
container.

### Automating the app server

"What if I want to automate starting the app too?" Well, in the case of Django
you can use [`LiveServerTestCase`](https://docs.djangoproject.com/en/1.8/topics/testing/tools/#liveservertestcase). The trick there is overriding the default
ip:port the server is bound to. In my case I set
`os.environ['DJANGO_LIVE_TEST_SERVER_ADDRESS']` in my ready callback method
based on info in the container inspection data.

## Contributors

* Jay Luker \<<jay_luker@harvard.edu>\> [@lbjay](http://github.com/lbjay)
* Matthieu Chevrier [@treemo](http://github.com/treemo)

## License

Apache 2.0

## Copyright

2015 President and Fellows of Harvard College
