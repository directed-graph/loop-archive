from typing import Iterable, Iterator, Optional

import pathlib
import shutil
import subprocess
import tempfile

from absl import app
from absl import flags
from absl import logging
from google.protobuf import text_format

import loop_archive_pb2

_CONFIG_FILE = flags.DEFINE_string(
    'config_file', None, 'Textproto containing a loop_archive.Config proto.')

_DRY_RUN = flags.DEFINE_bool('dry_run', False,
                             'Run everything in dry-run mode.')

_DRY_RUN_LOOP = flags.DEFINE_bool('dry_run_loop', False,
                                  'Run loop archival in dry-run mode.')


class MountError(RuntimeError):
  """Exception for errors when mounting.

  We have a separate class so we can behave differently when the RuntimeErorr
  is due to failure in mounting.
  """
  pass


def _run_process(args: Iterable[str]) -> subprocess.CompletedProcess:
  """Runs the given argument and log results."""
  args = list(args)  # May be an iterator.

  logging.info('Running command: %s', args)
  if _DRY_RUN.value:
    logging.info('DRY RUN: not running command')
    process = subprocess.CompletedProcess(
        args, 0, stdout=''.encode(), stderr=''.encode())
  else:
    process = subprocess.run(args, capture_output=True)

  logger = logging.info
  if process.returncode != 0:
    logger = logging.error
  logger('Return code: %s\nstdout: %s\nstderr: %s', str(process.returncode),
         process.stdout.decode(), process.stderr.decode())

  return process


def mount(device_path: pathlib.Path,
          mount_path: pathlib.Path,
          options: Optional[Iterable[str]] = None) -> None:
  """Mounts device_path to mount_path."""
  args = ['sudo', 'mount']
  if options is not None:
    args.append('-o')
    args.append(','.join(options))
  args.append(str(device_path))
  args.append(str(mount_path))

  process = _run_process(args)

  if process.returncode != 0:
    raise MountError(f'Mount failed for {device_path} <- {mount_path}.')


def umount(mount_path: pathlib.Path) -> None:
  """Unmounts mount_path."""
  args = [
      'sudo',
      'umount',
      str(mount_path),
  ]

  process = _run_process(args)

  if process.returncode != 0:
    raise RuntimeError(f'Umount failed for {mount_path}.')


class SourcePathContext:
  """Context Manager for a given SourceSpec.

  Given a SourceSpec, entering this context sets up the path for the source.
  Exiting the context cleans up the path.
  """

  def __init__(self, source_spec: loop_archive_pb2.SourceSpec):
    self.source_spec = source_spec
    self.source_path = None

  def setup_source_spec(self) -> pathlib.Path:
    """Sets up SourceSpec to a pathlib.Path."""
    if self.source_path is not None:
      raise RuntimeError('Cannot setup; already setup with {self.source_path}.')

    which_location = self.source_spec.WhichOneof('location')
    if which_location == 'storage_device':
      storage_device = self.source_spec.storage_device
      if not storage_device.path_format:
        storage_device.path_format = '/dev/disk/by-uuid/%s'
      device_path = pathlib.Path(storage_device.path_format %
                                 (storage_device.uuid,))
      mount_options = storage_device.mount_options
      self.source_path = pathlib.Path(tempfile.mkdtemp())
      mount(device_path, self.source_path, options=mount_options)
    else:
      raise ValueError(f'Unsupported SourceSpec.location: {which_location}')

    return self.source_path

  def teardown_source_spec(self) -> None:
    """Tears down a SourceSpec; the reverse of setup_source_spec."""
    which_location = self.source_spec.WhichOneof('location')
    if which_location == 'storage_device':
      umount(self.source_path)
      self.source_path.rmdir()
    else:
      raise ValueError(f'Unsupported SourceSpec.location: {which_location}')

    self.source_path = None

  def __enter__(self) -> pathlib.Path:
    return self.setup_source_spec()

  def __exit__(self, exc_type, exc_value, traceback) -> None:
    self.teardown_source_spec()


def get_directory_size(path: pathlib.Path) -> int:
  """Returns the size of the directory in bytes."""
  return sum(item.stat().st_size for item in path.rglob('*'))


def make_directory_iterator(path: pathlib.Path) -> Iterator[pathlib.Path]:
  """Returns an iterator that iterates from oldest file in directory."""
  yield from sorted(path.rglob('*'), key=lambda item: item.stat().st_mtime)


def archive_move(source_path: pathlib.Path, destination_path: pathlib.Path,
                 patterns: Iterable[str]) -> None:
  """Archives items by moving them to the destination."""
  for pattern in patterns:
    for item in source_path.glob(pattern):
      logging.info('Archiving (moving) %s -> %s.', item, destination_path)
      if _DRY_RUN.value or _DRY_RUN_LOOP.value:
        logging.info('DRY RUN: not moving.')
        continue
      shutil.copy2(item, destination_path / item.name)
      item.unlink()


def loop_delete(destination_path: pathlib.Path, loop_size: int) -> None:
  """Deletes old items to make more space for archiving."""
  deletion_iterator = make_directory_iterator(destination_path)
  while get_directory_size(destination_path) > loop_size:
    deletion_candidate = next(deletion_iterator)
    logging.info('Looping (deleting) %s', deletion_candidate)
    if _DRY_RUN.value or _DRY_RUN_LOOP.value:
      logging.info('DRY RUN: not deleting, not checking the rest.')
      break
    deletion_candidate.unlink()


def archive_delete(source_path: pathlib.Path, patterns: Iterable[str]) -> None:
  """Archives items by deleting them."""
  for pattern in patterns:
    for item in source_path.glob(pattern):
      logging.info('Archiving (deleting) %s.', item)
      if _DRY_RUN.value or _DRY_RUN_LOOP.value:
        logging.info('DRY RUN: not deleting.')
        continue
      item.unlink()


def archive(source_spec: loop_archive_pb2.SourceSpec,
            destination_spec: loop_archive_pb2.DestinationSpec) -> None:
  """Archives source_spec to destination_spec."""
  destination_path = pathlib.Path(destination_spec.path)
  if not destination_path.exists() or not destination_path.is_dir():
    raise ValueError('{destination_path} does not exist or is not a directory.')

  with SourcePathContext(source_spec) as source_path:
    logging.info('Archive moving %s to %s for patterns %s.', source_path,
                 destination_path, source_spec.patterns)
    archive_move(source_path, destination_path, source_spec.patterns)
    logging.info('Loop deleting %s to size %s.', destination_path,
                 destination_spec.loop_size)
    loop_delete(destination_path, destination_spec.loop_size)
    logging.info('Archive deleting %s for patterns %s.', source_path,
                 source_spec.delete_patterns)
    archive_delete(source_path, source_spec.delete_patterns)


def main(argv) -> None:
  del argv

  if not _CONFIG_FILE.value:
    raise ValueError('Must provide a config file.')

  config = loop_archive_pb2.Config()
  with open(_CONFIG_FILE.value) as stream:
    text_format.Parse(stream.read(), config)

  logging.info('Processing loop_archive.Config:\n%s', str(config))
  for source_spec in config.source_specs:
    try:
      archive(source_spec, config.destination_spec)
    except MountError as error:
      logging.warning('Failed to mount; skipping: %s', error)


if __name__ == '__main__':
  app.run(main)
