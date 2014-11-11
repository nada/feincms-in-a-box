from __future__ import unicode_literals

import os
import platform

from fabric.api import env, execute, hosts, settings, task
from fabric.colors import green, red
from fabric.contrib.project import rsync_project
from fabric.utils import puts

from fabfile import confirm, local, require_env, require_services
from fabfile.utils import get_random_string


@task(default=True)
@hosts('')
@require_services
def initial_setup():
    """Initial setup of the project. Use ``setup_with_production_data`` instead
    if the project is already installed on a server"""
    if os.path.exists('venv'):
        puts(red('It seems that this project is already set up, aborting.'))
        return 1

    execute('setup_local.create_virtualenv')
    execute('setup_local.frontend_tools')
    execute('setup_local.create_dotenv')
    execute('setup_local.create_and_migrate_database')

    puts(green(
        'Initial setup has completed successfully!', bold=True))
    puts(green(
        'Next steps:'))
    puts(green(
        '- Update the README: edit README.rst'))
    puts(green(
        '- Create a superuser: venv/bin/python manage.py createsuperuser'))
    puts(green(
        '- Run the development server: fab dev'))
    puts(green(
        '- Create a Bitbucket repository: fab versioning.init_bitbucket'))
    puts(green(
        '- Configure %(box_server_name)s for this project: fab setup_server'
        % env))


@task
@require_env
@require_services
def setup_with_production_data():
    """Installs all dependencies and pulls the database and mediafiles from
    the server to create an instant replica of the production environment"""
    if os.path.exists('venv'):
        puts(red('It seems that this project is already set up, aborting.'))
        return 1

    execute('setup_local.create_virtualenv')
    execute('setup_local.frontend_tools')
    execute('setup_local.create_dotenv')
    execute('setup_local.pull_database')
    execute('setup_local.pull_mediafiles')

    puts(green(
        'Setup with production data has completed successfully!', bold=True))
    puts(green(
        'Next steps:'))
    puts(green(
        '- Create a superuser: venv/bin/python manage.py createsuperuser'))
    puts(green(
        '- Run the development server: fab dev'))


@task
@hosts('')
def create_virtualenv():
    """Creates the virtualenv and installs all Python requirements"""
    local(
        'virtualenv --python python2.7'
        ' --prompt "(venv:%(box_domain)s)" venv')
    local('venv/bin/pip install -U wheel setuptools pip')
    if platform.system() == 'Darwin' and platform.mac_ver()[0] >= '10.9':
        local(
            'export CFLAGS=-Qunused-arguments'
            ' && export CPPFLAGS=-Qunused-arguments'
            ' && venv/bin/pip install -r requirements/dev.txt')
    else:
        local('venv/bin/pip install -r requirements/dev.txt')


@task
@hosts('')
def frontend_tools():
    """Installs frontend tools. Knows how to handle npm/bower and bundler"""
    if os.path.exists('bower.json'):
        local('npm install')
        local('bower install')
    elif os.path.exists('%(box_staticfiles)s/bower.json' % env):
        local('cd %(box_staticfiles)s && npm install')
        local('cd %(box_staticfiles)s && bower install')
    elif os.path.exists('%(box_staticfiles)s/config.rb' % env):
        local('bundle install --path=.bundle/gems')
    local('cp %(box_staticfiles)s/bower_components/foundation/scss/foundation/_settings.scss %(box_staticfiles)s/scss/')


@task
@hosts('')
def create_dotenv():
    """Creates a .env file containing basic configuration for
    local development"""
    with open('.env', 'w') as f:
        env.box_secret_key = get_random_string(50)
        f.write('''\
DATABASE_URL=postgres://localhost:5432/%(box_database_local)s
CACHE_URL=hiredis://localhost:6379/1/%(box_database_local)s
SECRET_KEY=%(box_secret_key)s
SENTRY_DSN=
''' % env)


@task
@hosts('')
@require_services
def create_and_migrate_database():
    """Creates and migrates a Postgres database"""
    local(
        'createdb %(box_database_local)s'
        ' --encoding=UTF8 --template=template0')
    local('venv/bin/python manage.py migrate')


@task
@require_env
@require_services
def pull_database():
    """Pulls the database contents from the server, dropping the local
    database first (if it exists)"""

    if not confirm(
            'Completely replace the local database'
            ' "%(box_database_local)s" (if it exists)?'):
        return

    with settings(warn_only=True):
        local('dropdb %(box_database_local)s')

    local(
        'createdb %(box_database_local)s'
        ' --encoding=UTF8 --template=template0')
    local(
        'ssh %(box_server)s "source .profile &&'
        ' pg_dump %(box_database)s'
        ' --no-privileges --no-owner --no-reconnect"'
        ' | psql %(box_database_local)s')
    local(
        'psql %(box_database_local)s -c "UPDATE auth_user'
        ' SET password=\'pbkdf2_sha256\$12000\$owbr7vjRCspg\$PAo53Cbqvek3nMqS'
        'l+V+ubIlnZQ2Vj7ZVKcPhcXqWlY=\''
        ' WHERE password=\'\'"')
    puts(green(
        'Users with empty passwords (for example SSO users) now have a'
        ' password of "password" (without quotes).'))


@task
@require_env
def pull_mediafiles():
    """Pulls all mediafiles from the server. Beware, it is possible that this
    command pulls down several GBs!"""
    if not confirm('Completely replace local mediafiles?'):
        return
    rsync_project(
        local_dir='media/',
        remote_dir='%(box_domain)s/media/' % env,
        delete=False,  # Devs can take care of their media folders.
        upload=False,
    )
