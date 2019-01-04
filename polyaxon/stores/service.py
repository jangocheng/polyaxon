import os
import shutil

from hestia.service_interface import InvalidService, Service
from marshmallow import ValidationError
from polystores import StoreManager
from rhea import RheaError

from django.conf import settings

from libs.paths.experiment_jobs import create_experiment_job_path
from libs.paths.experiments import create_experiment_path
from libs.paths.jobs import create_job_path
from libs.paths.utils import check_archive_path, create_path, delete_path
from polyaxon.config_manager import config
from stores.exceptions import VolumeNotFoundError
from stores.schemas.store import StoreConfig
from stores.schemas.volume import VolumeConfig
from stores.store_secrets import get_store_secret_for_persistence, get_store_secret_from_definition
from stores.validators import validate_persistence_data, validate_persistence_outputs


class StoresService(Service):
    __all__ = (
        'setup',
        'validate',
        'get_data_paths',
        'get_data_path',
        'delete_data_path',
        'get_logs_path',
        'get_outputs_path',
        'delete_outputs_path',
        'get_logs_path',
        'delete_logs_path',
        'get_outputs_store',
        'get_logs_store',
        'get_experiment_group_outputs_path',
        'get_experiment_group_logs_path',
        'get_experiment_job_logs_path',
        'get_experiment_outputs_path',
        'get_experiment_logs_path',
        'get_job_outputs_path',
        'get_job_logs_path',
        'get_notebook_job_outputs_path',
        'get_project_outputs_path',
        'get_project_logs_path',
        'create_experiment_logs_path',
        'create_experiment_outputs_path',
        'create_experiment_job_logs_path',
        'copy_experiment_outputs',
        'create_job_logs_path',
        'create_job_outputs_path'
    )

    @staticmethod
    def get_data_paths(persistences):
        persistence_data = validate_persistence_data(persistence_data=persistences)
        persistence_paths = {}
        for persistence in persistence_data:
            if persistence not in settings.PERSISTENCE_DATA:
                raise VolumeNotFoundError(
                    'Data volume with name `{}` was defined in specification, '
                    'but was not found'.format(persistence))
            persistence_type_condition = (
                'mountPath' not in settings.PERSISTENCE_DATA[persistence] and
                'bucket' not in settings.PERSISTENCE_DATA[persistence]
            )
            if persistence_type_condition:
                raise VolumeNotFoundError(
                    'Data volume with name `{}` '
                    'does not define a mountPath or bucket.'.format(persistence))

            persistence_paths[persistence] = (
                settings.PERSISTENCE_DATA[persistence].get('mountPath') or
                settings.PERSISTENCE_DATA[persistence].get('bucket'))

        return persistence_paths

    @classmethod
    def get_data_path(cls, persistence):
        persistences = [persistence] if persistence else None
        paths = cls.get_data_paths(persistences=persistences)
        return list(paths.values())[0]

    @classmethod
    def delete_data_path(cls, subpath, persistence):
        data_path = cls.get_data_path(persistence=persistence)
        path = os.path.join(data_path, subpath)
        delete_path(path)

    @staticmethod
    def get_outputs_path(persistence):
        persistence_outputs = validate_persistence_outputs(persistence_outputs=persistence)
        if persistence_outputs not in settings.PERSISTENCE_OUTPUTS:
            raise VolumeNotFoundError('Outputs volume with name `{}` was defined in specification, '
                                      'but was not found'.format(persistence_outputs))
        persistence_type_condition = (
            'mountPath' not in settings.PERSISTENCE_OUTPUTS[persistence_outputs] and
            'bucket' not in settings.PERSISTENCE_OUTPUTS[persistence_outputs]
        )
        if persistence_type_condition:
            raise VolumeNotFoundError(
                'Outputs volume with name `{}` '
                'does not define a mountPath or bucket.'.format(persistence_outputs))

        return (settings.PERSISTENCE_OUTPUTS[persistence_outputs].get('mountPath') or
                settings.PERSISTENCE_OUTPUTS[persistence_outputs].get('bucket'))

    @classmethod
    def delete_outputs_path(cls, subpath, persistence):
        outputs_path = cls.get_outputs_path(persistence=persistence)
        path = os.path.join(outputs_path, subpath)
        delete_path(path)

    @staticmethod
    def get_logs_path(persistence='default'):
        persistence_type_condition = (
            'mountPath' not in settings.PERSISTENCE_LOGS and
            'bucket' not in settings.PERSISTENCE_LOGS
        )
        if persistence_type_condition:
            raise VolumeNotFoundError('Logs volume does not define a mountPath or bucket.')

        return settings.PERSISTENCE_LOGS.get('mountPath') or settings.PERSISTENCE_LOGS.get('bucket')

    @classmethod
    def delete_logs_path(cls, subpath, persistence='default'):
        outputs_path = cls.get_logs_path(persistence=persistence)
        path = os.path.join(outputs_path, subpath)
        delete_path(path)

    @staticmethod
    def _get_store(store, secret_key):
        if not store or not secret_key:
            return StoreManager()
        try:
            store_access = config.get_dict(secret_key)
        except RheaError:
            raise VolumeNotFoundError(
                'Could not create store for path,'
                'received a store type `{}` without valid access key.'.format(store))

        return StoreManager.get_for_type(store_type=store, store_access=store_access)

    @classmethod
    def get_outputs_store(cls, persistence_outputs):
        store, _, secret_key = get_store_secret_for_persistence(
            volume_name=persistence_outputs,
            volume_settings=settings.PERSISTENCE_OUTPUTS)
        return cls._get_store(store, secret_key)

    @classmethod
    def get_logs_store(cls, persistence_logs='default'):
        store, _, secret_key = get_store_secret_from_definition(settings.PERSISTENCE_LOGS)
        return cls._get_store(store, secret_key)

    @classmethod
    def get_experiment_group_outputs_path(cls, experiment_group_name, persistence):
        persistence_outputs = cls.get_outputs_path(persistence=persistence)
        values = experiment_group_name.split('.')
        values.insert(2, 'groups')
        return os.path.join(persistence_outputs, '/'.join(values))

    @classmethod
    def get_experiment_group_logs_path(cls, experiment_group_name, persistence='default'):
        values = experiment_group_name.split('.')
        values.insert(2, 'groups')
        persistence_logs = cls.get_logs_path(persistence=persistence)
        return os.path.join(persistence_logs, '/'.join(values))

    @classmethod
    def get_experiment_job_logs_path(cls, experiment_job_name, temp, persistence='default'):
        values = experiment_job_name.split('.')
        values = values[:-2] + ['.'.join(values[-2:])]
        if len(values) == 4:
            values.insert(2, 'experiments')
        else:
            values.insert(2, 'groups')

        if temp:
            return os.path.join(settings.LOGS_ARCHIVE_ROOT, '/'.join(values))
        persistence_logs = cls.get_logs_path(persistence=persistence)
        return os.path.join(persistence_logs, '/'.join(values))

    @classmethod
    def get_experiment_outputs_path(cls,
                                    persistence,
                                    experiment_name,
                                    original_name=None,
                                    cloning_strategy=None):
        from db.models.cloning_strategies import CloningStrategy

        persistence_outputs = cls.get_outputs_path(persistence=persistence)
        values = experiment_name.split('.')
        if original_name is not None and cloning_strategy == CloningStrategy.RESUME:
            values = original_name.split('.')
        if len(values) == 3:
            values.insert(2, 'experiments')
        else:
            values.insert(2, 'groups')
        return os.path.join(persistence_outputs, '/'.join(values))

    @classmethod
    def get_experiment_logs_path(cls, experiment_name, temp, persistence='default'):
        values = experiment_name.split('.')
        if len(values) == 3:
            values.insert(2, 'experiments')
        else:
            values.insert(2, 'groups')

        if temp:
            return os.path.join(settings.LOGS_ARCHIVE_ROOT, '/'.join(values))
        persistence_logs = cls.get_logs_path(persistence=persistence)
        return os.path.join(persistence_logs, '/'.join(values))

    @classmethod
    def get_job_outputs_path(cls, persistence, job_name):
        persistence_outputs = cls.get_outputs_path(persistence=persistence)
        return os.path.join(persistence_outputs, job_name.replace('.', '/'))

    @classmethod
    def get_job_logs_path(cls, job_name, temp, persistence='default'):
        if temp:
            return os.path.join(settings.LOGS_ARCHIVE_ROOT, job_name.replace('.', '/'))
        persistence_logs = cls.get_logs_path(persistence=persistence)
        return os.path.join(persistence_logs, job_name.replace('.', '/'))

    @classmethod
    def create_experiment_job_logs_path(cls, experiment_job_name, temp, persistence='default'):
        if temp:
            check_archive_path(settings.LOGS_ARCHIVE_ROOT)
            return create_experiment_job_path(experiment_job_name, settings.LOGS_ARCHIVE_ROOT)
        persistence_logs = cls.get_logs_path(persistence=persistence)
        return create_experiment_job_path(experiment_job_name, persistence_logs)

    @classmethod
    def get_notebook_job_outputs_path(cls, persistence, notebook_job):
        persistence_outputs = cls.get_outputs_path(persistence=persistence)
        return os.path.join(persistence_outputs, notebook_job.replace('.', '/'))

    @classmethod
    def get_project_outputs_path(cls, persistence, project_name):
        persistence_outputs = cls.get_outputs_path(persistence=persistence)
        return os.path.join(persistence_outputs, project_name.replace('.', '/'))

    @classmethod
    def get_project_logs_path(cls, project_name, persistence='default'):
        persistence_logs = cls.get_logs_path(persistence=persistence)
        return os.path.join(persistence_logs, project_name.replace('.', '/'))

    @classmethod
    def create_experiment_logs_path(cls, experiment_name, temp, persistence='default'):
        if temp:
            check_archive_path(settings.LOGS_ARCHIVE_ROOT)
            return create_experiment_path(experiment_name, settings.LOGS_ARCHIVE_ROOT)

        persistence_logs = cls.get_logs_path(persistence=persistence)
        return create_experiment_path(experiment_name, persistence_logs)

    @classmethod
    def create_experiment_outputs_path(cls, persistence, experiment_name):
        persistence_outputs = cls.get_outputs_path(persistence=persistence)
        values = experiment_name.split('.')
        path = create_experiment_path(experiment_name, persistence_outputs)
        path = os.path.join(path, values[-1])
        if not os.path.isdir(path):
            create_path(path)
        return path

    @classmethod
    def copy_experiment_outputs(cls,
                                persistence_outputs_from,
                                persistence_outputs_to,
                                experiment_name_from,
                                experiment_name_to):
        path_from = cls.get_experiment_outputs_path(persistence_outputs_from,
                                                    experiment_name_from)
        path_to = cls.get_experiment_outputs_path(persistence_outputs_to, experiment_name_to)
        shutil.copytree(path_from, path_to)

    @classmethod
    def create_job_logs_path(cls, job_name, temp, persistence='default'):
        if temp:
            check_archive_path(settings.LOGS_ARCHIVE_ROOT)
            return create_job_path(job_name, settings.LOGS_ARCHIVE_ROOT)
        persistence_logs = cls.get_logs_path(persistence=persistence)
        return create_job_path(job_name, persistence_logs)

    @classmethod
    def create_job_outputs_path(cls, persistence, job_name):
        persistence_outputs = cls.get_outputs_path(persistence=persistence)
        values = job_name.split('.')
        path = create_job_path(job_name, persistence_outputs)
        path = os.path.join(path, values[-1])
        if not os.path.isdir(path):
            create_path(path)
        return path

    @staticmethod
    def _validate_persistence(persistence, persistence_name, persistence_type):
        try:
            VolumeConfig.from_dict(persistence)
        except ValidationError:
            try:
                StoreConfig.from_dict(persistence)
            except (ValidationError, TypeError):
                raise InvalidService('Persistence `{}`, of type `{}`, is not valid.'.format(
                    persistence_name, persistence_type
                ))

    def _validate_logs(self):
        self._validate_persistence(persistence=settings.PERSISTENCE_LOGS,
                                   persistence_name='default',
                                   persistence_type='PERSISTENCE_LOGS')

    def _validate_outputs(self):
        for persistence_name, persistence in settings.PERSISTENCE_OUTPUTS.items():
            self._validate_persistence(persistence=persistence,
                                       persistence_name=persistence_name,
                                       persistence_type='PERSISTENCE_OUTPUTS')

    def _validate_data(self):
        for persistence_name, persistence in settings.PERSISTENCE_DATA.items():
            self._validate_persistence(persistence=persistence,
                                       persistence_name=persistence_name,
                                       persistence_type='PERSISTENCE_DATA')

    def validate(self):
        self._validate_logs()
        self._validate_outputs()
        self._validate_data()
