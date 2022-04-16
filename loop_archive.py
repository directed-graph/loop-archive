from typing import Iterable, Iterator, Optional

import pathlib
import subprocess
import tempfile

from absl import flags
from absl import logging

import loop_archive_pb2

_DRY_RUN = flags.DEFINE_bool('dry_run', False,
                             'Run everything in dry-run mode.')


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
    raise RuntimeError(f'Mount failed for {device_path} <- {mount_path}.')


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
      device_path = pathlib.Path(f'/dev/disk/by-uuid/{storage_device.uuid}')
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
