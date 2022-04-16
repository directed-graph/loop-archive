from unittest import mock

import functools
import os
import pathlib
import re
import subprocess
import tempfile

from absl.testing import absltest
from absl.testing import flagsaver
from absl.testing import parameterized
from google.protobuf import text_format
from rules_python.python.runfiles import runfiles

import loop_archive
import loop_archive_pb2


class LoopArchiveTest(parameterized.TestCase):
  """Unit tests for loop_archive."""

  def test_mount(self):
    """Tests mount operation."""
    device_path = pathlib.Path('/dev/device/path')
    mount_path = pathlib.Path('/mnt/mount/path')
    options = ['opt0', 'opt1', 'opt2']
    with mock.patch.object(
        loop_archive, '_run_process', autospec=True) as mock_run_process:
      mock_run_process.return_value = subprocess.CompletedProcess(
          args=mock.ANY, returncode=0)
      loop_archive.mount(device_path, mount_path, options)
    mock_run_process.assert_called_with([
        'sudo',
        'mount',
        '-o',
        ','.join(options),
        str(device_path),
        str(mount_path),
    ])

  def test_umount(self):
    """Tests umount operation."""
    mount_path = pathlib.Path('/mnt/mount/path')
    with mock.patch.object(
        loop_archive, '_run_process', autospec=True) as mock_run_process:
      mock_run_process.return_value = subprocess.CompletedProcess(
          args=mock.ANY, returncode=0)
      loop_archive.umount(mount_path)
    mock_run_process.assert_called_with([
        'sudo',
        'umount',
        str(mount_path),
    ])

  @parameterized.parameters(
      functools.partial(loop_archive.mount, pathlib.Path('.'),
                        pathlib.Path('.'), []),
      functools.partial(loop_archive.umount, pathlib.Path('.')),
  )
  def test_mount_umount_failure(self, mount_or_umount_partial):
    """Tests failed mount and umount operations."""
    with mock.patch.object(
        loop_archive, '_run_process', autospec=True) as mock_run_process:
      mock_run_process.return_value = subprocess.CompletedProcess(
          args=mock.ANY, returncode=1)
      with self.assertRaises(RuntimeError):
        mount_or_umount_partial()

  @mock.patch.object(loop_archive, 'mount', autospec=True)
  @mock.patch.object(loop_archive, 'umount', autospec=True)
  def test_source_path_context(self, mock_umount, mock_mount):
    """Ensures proper setup and teardown of SourcePathContext."""
    device_uuid = 'test-uuid'
    mount_options = ['umask=000']
    source_spec = loop_archive_pb2.SourceSpec(
        storage_device=loop_archive_pb2.SourceSpec.StorageDevice(
            uuid=device_uuid,
            mount_options=mount_options,
        ))

    with loop_archive.SourcePathContext(source_spec) as source_path:
      self.assertTrue(source_path.is_dir())

    mock_mount.assert_called_with(
        pathlib.Path(f'/dev/disk/by-uuid/{device_uuid}'), source_path,
        mount_options)
    mock_umount.assert_called_with(source_path)
    self.assertFalse(source_path.exists())


if __name__ == '__main__':
  absltest.main()
