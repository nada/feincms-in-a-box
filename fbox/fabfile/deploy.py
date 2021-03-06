from __future__ import unicode_literals

import os

from fabric.api import env, execute, task
from fabric.colors import red
from fabric.contrib.project import rsync_project
from fabric.utils import abort

from fabfile import run_local, cd, require_env, run, step


@task(default=True)
@require_env
def deploy():
    """Deploys frontend and backend code to the server if the checking step
    did not report any problems"""
    execute('check.deploy')
    execute('deploy.styles')
    execute('deploy.code')


def _deploy_styles_foundation5_gulp():
    run_local('./node_modules/.bin/gulp build')
    for part in ['bower_components', 'build']:
        rsync_project(
            local_dir='%(box_staticfiles)s/%(part)s' % dict(env, part=part),
            remote_dir='%(box_domain)s/%(box_staticfiles)s/' % env,
            delete=True,
        )


def _deploy_styles_foundation5_grunt():
    run_local('cd %(box_staticfiles)s && grunt build')
    for part in ['bower_components', 'css']:
        rsync_project(
            local_dir='%(box_staticfiles)s/%(part)s' % dict(env, part=part),
            remote_dir='%(box_domain)s/%(box_staticfiles)s/' % env,
            delete=True,
        )


def _deploy_styles_foundation4_bundler():
    run_local('bundle exec compass clean %(box_staticfiles)s')
    run_local('bundle exec compass compile -s compressed %(box_staticfiles)s')
    rsync_project(
        local_dir='%(box_staticfiles)s/stylesheets' % env,
        remote_dir='%(box_domain)s/%(box_staticfiles)s/' % env,
        delete=True,
    )


@task
@require_env
def styles():
    """Compiles and compresses the CSS and deploys it to the server"""
    execute('check.deploy')

    step('\nBuilding and deploying assets...')

    if os.path.exists('gulpfile.js'):
        _deploy_styles_foundation5_gulp()
    elif os.path.exists('%(box_staticfiles)s/Gulpfile.js' % env):
        _deploy_styles_foundation5_grunt()
    elif os.path.exists('%(box_staticfiles)s/config.rb' % env):
        _deploy_styles_foundation4_bundler()
    else:
        abort(red('I do not know how to deploy this frontend code.'))

    with cd('%(box_domain)s'):
        run('venv/bin/python manage.py collectstatic --noinput')


@task
@require_env
def code():
    """Deploys the currently committed project state to the server, if there
    are no uncommitted changes on the server and the checking step did not
    report any problems"""
    execute('check.deploy')

    # XXX Maybe abort deployment if branch-to-be-deployed is not checked out?

    step('\nPushing changes...')
    run_local('git push origin %(box_branch)s')

    step('\nDeploying new code on server...')
    with cd('%(box_domain)s'):
        run('git fetch')
        run('git reset --hard origin/%(box_branch)s')
        run('find . -name "*.pyc" -delete')
        run('venv/bin/pip install -r requirements/production.txt'
            ' --find-links file:///home/www-data/tmp/wheel/wheelhouse/')
        run('venv/bin/python manage.py migrate --noinput')
        run('venv/bin/python manage.py collectstatic --noinput')
        run('sctl restart %(box_domain)s:*')

    execute('git.fetch_remote')
