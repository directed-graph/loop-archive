from typing import Iterable, List
from unittest import mock

import dataclasses
import functools
import os
import pathlib
import subprocess
import tempfile

from absl.testing import absltest
from absl.testing import flagsaver
from absl.testing import parameterized

import loop_archive
import loop_archive_pb2


@dataclasses.dataclass
class TestDirectoryTree:
  path: pathlib.Path
  generate_order: List[pathlib.Path]
  generate_mtime: List[int]

  # Size in bytes.
  size: int


class DirectoryTreeContext:
  """Context to generate a directory tree with items for testing."""

  def __init__(self, num_items: int = 16, suffixes: Iterable[str] = None):
    """Initializes the TestDirectoryTree Context.

    Args:
      num_items: The number of items to generate.
      suffixes: The suffix of each item. Determines the number of items to
          generate if set; i.e. num_items will be ignored.
    """
    self.num_items = num_items
    self.suffixes = suffixes
    if self.suffixes is None:
      self.suffixes = range(num_items)

  def __enter__(self) -> TestDirectoryTree:
    self.temp_dir = tempfile.TemporaryDirectory()
    test_directory_tree = TestDirectoryTree(
        path=pathlib.Path(self.temp_dir.name),
        generate_order=[],
        generate_mtime=[],
        size=0,
    )
    mtime = 0
    for suffix in self.suffixes:
      item = test_directory_tree.path / f'file{suffix}'
      with open(item, 'w') as stream:
        test_directory_tree.size += stream.write('0')

      # Manually set time so each file has different mtimes.
      os.utime(item, (0, mtime))
      test_directory_tree.generate_order.append(item)
      test_directory_tree.generate_mtime.append(mtime)

      mtime += 1

    return test_directory_tree

  def __exit__(self, exec_type, exec_value, traceback) -> None:
    self.temp_dir.cleanup()


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

  def test_get_directory_size(self):
    """Ensures count is correct."""
    with DirectoryTreeContext() as directory_tree:
      self.assertEqual(
          loop_archive.get_directory_size(directory_tree.path),
          directory_tree.size)

  def test_make_directory_iterator(self):
    """Ensures order is correct."""
    with DirectoryTreeContext() as directory_tree:
      self.assertEqual(
          list(loop_archive.make_directory_iterator(directory_tree.path)),
          directory_tree.generate_order)

  def test_archive_move(self):
    """Tests archive moving items are done correctly."""
    temp_output_dir = tempfile.TemporaryDirectory()
    output_dir = pathlib.Path(temp_output_dir.name)

    with DirectoryTreeContext(suffixes=[f'{i}.MP4' for i in range(5)] +
                              [f'{i}.THM' for i in range(5)]) as directory_tree:
      loop_archive.archive_move(
          directory_tree.path, output_dir, patterns=['*.MP4'])
      # Ensures the .MP4 files are moved.
      self.assertCountEqual(
          map(lambda p: p.name, output_dir.glob('*')),
          map(lambda p: p.name, directory_tree.generate_order[:5]))
      # Ensures the .THM files are not moved.
      self.assertCountEqual(
          map(lambda p: p.name, directory_tree.path.glob('*')),
          map(lambda p: p.name, directory_tree.generate_order[5:]))

    temp_output_dir.cleanup()

  def test_archive_delete(self):
    """Tests archive deleting items are done correctly."""
    with DirectoryTreeContext(suffixes=[f'{i}.MP4' for i in range(5)] +
                              [f'{i}.THM' for i in range(5)]) as directory_tree:
      loop_archive.archive_delete(directory_tree.path, patterns=['*.THM'])
      # Ensures the .THM files are deleted.
      self.assertCountEqual(
          map(lambda p: p.name, directory_tree.path.glob('*')),
          map(lambda p: p.name, directory_tree.generate_order[:5]))

  def test_loop_delete(self):
    """Tests loop deleting items are done correctly."""
    with DirectoryTreeContext() as directory_tree:
      # Sets loop_size to only the length of 2 items.
      loop_archive.loop_delete(
          directory_tree.path,
          loop_size=2 * directory_tree.size /
          len(directory_tree.generate_order))
      self.assertLen(list(directory_tree.path.glob('*')), 2)

  def test_archive(self):
    """Simulates an archive operation."""
    temp_output_dir = tempfile.TemporaryDirectory()
    output_dir = pathlib.Path(temp_output_dir.name)

    with DirectoryTreeContext(suffixes=[f'{i}.MP4' for i in range(5)] +
                              [f'{i}.THM' for i in range(5)] +
                              [f'{i}.LRV' for i in range(5)]) as directory_tree:
      source_spec = loop_archive_pb2.SourceSpec(
          storage_device=loop_archive_pb2.SourceSpec.StorageDevice(
              uuid='test-uuid'),
          patterns=['*.MP4'],
          delete_patterns=['*.THM', '*.LRV'],
      )
      destination_spec = loop_archive_pb2.DestinationSpec(
          loop_size=2,
          path=str(output_dir),
      )

      # Mock the _run_process operation so mount and umount are noops.
      with mock.patch.object(
          loop_archive, 'SourcePathContext',
          autospec=True) as mock_source_path_context:
        mock_source_path_context.return_value = directory_tree.path
        loop_archive.archive(source_spec, destination_spec)
        self.assertEqual(
            list(map(lambda p: p.name, output_dir.glob('*'))),
            ['file3.MP4', 'file4.MP4'])
        self.assertEmpty(list(directory_tree.path.glob('*')))

      temp_output_dir.cleanup()


if __name__ == '__main__':
  absltest.main()
