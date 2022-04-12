from typing import Iterable, Iterator, Optional

import pathlib
import subprocess

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
