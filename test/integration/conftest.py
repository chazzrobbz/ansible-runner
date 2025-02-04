import os
import shutil
import subprocess
import json
import yaml

import pytest
import pexpect
from ansible_runner.config.runner import RunnerConfig


@pytest.fixture(scope='function')
def rc(tmp_path):
    rc = RunnerConfig(str(tmp_path))
    rc.suppress_ansible_output = True
    rc.expect_passwords = {
        pexpect.TIMEOUT: None,
        pexpect.EOF: None
    }
    rc.cwd = str(tmp_path)
    rc.env = {}
    rc.job_timeout = 10
    rc.idle_timeout = 0
    rc.pexpect_timeout = 2.
    rc.pexpect_use_poll = True
    return rc


# TODO: determine if we want to add docker / podman
# to zuul instances in order to run these tests
@pytest.fixture(scope="session", autouse=True)
def container_runtime_available():
    import subprocess
    import warnings

    runtimes_available = True
    for runtime in ('docker', 'podman'):
        try:
            subprocess.run([runtime, '-v'])
        except FileNotFoundError:
            warnings.warn(UserWarning(f"{runtime} not available"))
            runtimes_available = False
    return runtimes_available


# TODO: determine if we want to add docker / podman
# to zuul instances in order to run these tests
@pytest.fixture(scope="session")
def container_runtime_installed():
    import subprocess

    for runtime in ('podman', 'docker'):
        try:
            subprocess.run([runtime, '-v'])
            return runtime
        except FileNotFoundError:
            pass
    pytest.skip('No container runtime is available.')


@pytest.fixture(scope='session')
def clear_integration_artifacts(request):
    '''Fixture is session scoped to allow parallel runs without error
    '''
    if 'PYTEST_XDIST_WORKER' in os.environ:
        # we never want to clean artifacts if running parallel tests
        # because we cannot know when all processes are finished and it is
        # safe to clean up
        return

    def rm_integration_artifacts():
        path = "test/integration/artifacts"
        if os.path.exists(path):
            shutil.rmtree(path)

    request.addfinalizer(rm_integration_artifacts)


class CompletedProcessProxy(object):

    def __init__(self, result):
        self.result = result

    def __getattr__(self, attr):
        return getattr(self.result, attr)

    @property
    def json(self):
        try:
            response_json = json.loads(self.stdout)
        except json.JSONDecodeError:
            pytest.fail(
                f"Unable to convert the response to a valid json - stdout: {self.stdout}, stderr: {self.stderr}"
            )
        return response_json

    @property
    def yaml(self):
        return yaml.safe_load(self.stdout)


@pytest.fixture(scope='function')
def cli(request):
    def run(args, *a, **kw):
        if not kw.pop('bare', None):
            args = ['ansible-runner'] + args
        kw['encoding'] = 'utf-8'
        if 'check' not in kw:
            # By default we want to fail if a command fails to run. Tests that
            # want to skip this can pass check=False when calling this fixture
            kw['check'] = True
        if 'stdout' not in kw:
            kw['stdout'] = subprocess.PIPE
        if 'stderr' not in kw:
            kw['stderr'] = subprocess.PIPE

        kw.setdefault('env', os.environ.copy()).update({
            'LANG': 'en_US.UTF-8'
        })

        try:
            ret = CompletedProcessProxy(subprocess.run(' '.join(args), shell=True, *a, **kw))
        except subprocess.CalledProcessError as err:
            pytest.fail(
                f"Running {err.cmd} resulted in a non-zero return code: {err.returncode} - stdout: {err.stdout}, stderr: {err.stderr}"
            )

        return ret
    return run
