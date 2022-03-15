#
# Copyright (C) 2017 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os.path
import shutil

import common
import merge_target_files
import test_utils
from merge_target_files import (
    validate_config_lists, DEFAULT_FRAMEWORK_ITEM_LIST,
    DEFAULT_VENDOR_ITEM_LIST, DEFAULT_FRAMEWORK_MISC_INFO_KEYS, copy_items,
    item_list_to_partition_set, merge_package_keys_txt, compile_split_sepolicy,
    validate_merged_apex_info)


class MergeTargetFilesTest(test_utils.ReleaseToolsTestCase):

  def setUp(self):
    self.testdata_dir = test_utils.get_testdata_dir()
    self.OPTIONS = merge_target_files.OPTIONS
    self.OPTIONS.framework_item_list = DEFAULT_FRAMEWORK_ITEM_LIST
    self.OPTIONS.framework_misc_info_keys = DEFAULT_FRAMEWORK_MISC_INFO_KEYS
    self.OPTIONS.vendor_item_list = DEFAULT_VENDOR_ITEM_LIST
    self.OPTIONS.framework_partition_set = set(
        ['product', 'system', 'system_ext'])
    self.OPTIONS.vendor_partition_set = set(['odm', 'vendor'])

  def test_copy_items_CopiesItemsMatchingPatterns(self):

    def createEmptyFile(path):
      if not os.path.exists(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
      open(path, 'a').close()
      return path

    def createSymLink(source, dest):
      os.symlink(source, dest)
      return dest

    def getRelPaths(start, filepaths):
      return set(
          os.path.relpath(path=filepath, start=start) for filepath in filepaths)

    input_dir = common.MakeTempDir()
    output_dir = common.MakeTempDir()
    expected_copied_items = []
    actual_copied_items = []
    patterns = ['*.cpp', 'subdir/*.txt']

    # Create various files that we expect to get copied because they
    # match one of the patterns.
    expected_copied_items.extend([
        createEmptyFile(os.path.join(input_dir, 'a.cpp')),
        createEmptyFile(os.path.join(input_dir, 'b.cpp')),
        createEmptyFile(os.path.join(input_dir, 'subdir', 'c.txt')),
        createEmptyFile(os.path.join(input_dir, 'subdir', 'd.txt')),
        createEmptyFile(
            os.path.join(input_dir, 'subdir', 'subsubdir', 'e.txt')),
        createSymLink('a.cpp', os.path.join(input_dir, 'a_link.cpp')),
    ])
    # Create some more files that we expect to not get copied.
    createEmptyFile(os.path.join(input_dir, 'a.h'))
    createEmptyFile(os.path.join(input_dir, 'b.h'))
    createEmptyFile(os.path.join(input_dir, 'subdir', 'subsubdir', 'f.gif'))
    createSymLink('a.h', os.path.join(input_dir, 'a_link.h'))

    # Copy items.
    copy_items(input_dir, output_dir, patterns)

    # Assert the actual copied items match the ones we expected.
    for dirpath, _, filenames in os.walk(output_dir):
      actual_copied_items.extend(
          os.path.join(dirpath, filename) for filename in filenames)
    self.assertEqual(
        getRelPaths(output_dir, actual_copied_items),
        getRelPaths(input_dir, expected_copied_items))
    self.assertEqual(
        os.readlink(os.path.join(output_dir, 'a_link.cpp')), 'a.cpp')

  def test_validate_config_lists_ReturnsFalseIfMissingDefaultItem(self):
    self.OPTIONS.framework_item_list = list(DEFAULT_FRAMEWORK_ITEM_LIST)
    self.OPTIONS.framework_item_list.remove('SYSTEM/*')
    self.assertFalse(validate_config_lists())

  def test_validate_config_lists_ReturnsTrueIfDefaultItemInDifferentList(self):
    self.OPTIONS.framework_item_list = list(DEFAULT_FRAMEWORK_ITEM_LIST)
    self.OPTIONS.framework_item_list.remove('ROOT/*')
    self.OPTIONS.vendor_item_list = list(DEFAULT_VENDOR_ITEM_LIST)
    self.OPTIONS.vendor_item_list.append('ROOT/*')
    self.assertTrue(validate_config_lists())

  def test_validate_config_lists_ReturnsTrueIfExtraItem(self):
    self.OPTIONS.framework_item_list = list(DEFAULT_FRAMEWORK_ITEM_LIST)
    self.OPTIONS.framework_item_list.append('MY_NEW_PARTITION/*')
    self.assertTrue(validate_config_lists())

  def test_validate_config_lists_ReturnsFalseIfSharedExtractedPartition(self):
    self.OPTIONS.vendor_item_list = list(DEFAULT_VENDOR_ITEM_LIST)
    self.OPTIONS.vendor_item_list.append('SYSTEM/my_system_file')
    self.assertFalse(validate_config_lists())

  def test_validate_config_lists_ReturnsFalseIfSharedExtractedPartitionImage(
      self):
    self.OPTIONS.vendor_item_list = list(DEFAULT_VENDOR_ITEM_LIST)
    self.OPTIONS.vendor_item_list.append('IMAGES/system.img')
    self.assertFalse(validate_config_lists())

  def test_validate_config_lists_ReturnsFalseIfBadSystemMiscInfoKeys(self):
    for bad_key in ['dynamic_partition_list', 'super_partition_groups']:
      self.OPTIONS.framework_misc_info_keys = list(
          DEFAULT_FRAMEWORK_MISC_INFO_KEYS)
      self.OPTIONS.framework_misc_info_keys.append(bad_key)
      self.assertFalse(validate_config_lists())

  def test_merge_package_keys_txt_ReturnsTrueIfNoConflicts(self):
    output_meta_dir = common.MakeTempDir()

    framework_meta_dir = common.MakeTempDir()
    os.symlink(
        os.path.join(self.testdata_dir, 'apexkeys_framework.txt'),
        os.path.join(framework_meta_dir, 'apexkeys.txt'))

    vendor_meta_dir = common.MakeTempDir()
    os.symlink(
        os.path.join(self.testdata_dir, 'apexkeys_vendor.txt'),
        os.path.join(vendor_meta_dir, 'apexkeys.txt'))

    merge_package_keys_txt(framework_meta_dir, vendor_meta_dir, output_meta_dir,
                           'apexkeys.txt')

    merged_entries = []
    merged_path = os.path.join(self.testdata_dir, 'apexkeys_merge.txt')

    with open(merged_path) as f:
      merged_entries = f.read().split('\n')

    output_entries = []
    output_path = os.path.join(output_meta_dir, 'apexkeys.txt')

    with open(output_path) as f:
      output_entries = f.read().split('\n')

    return self.assertEqual(merged_entries, output_entries)

  def test_process_apex_keys_apk_certs_ReturnsFalseIfConflictsPresent(self):
    output_meta_dir = common.MakeTempDir()

    framework_meta_dir = common.MakeTempDir()
    os.symlink(
        os.path.join(self.testdata_dir, 'apexkeys_framework.txt'),
        os.path.join(framework_meta_dir, 'apexkeys.txt'))

    conflict_meta_dir = common.MakeTempDir()
    os.symlink(
        os.path.join(self.testdata_dir, 'apexkeys_framework_conflict.txt'),
        os.path.join(conflict_meta_dir, 'apexkeys.txt'))

    self.assertRaises(ValueError, merge_package_keys_txt, framework_meta_dir,
                      conflict_meta_dir, output_meta_dir, 'apexkeys.txt')

  def test_process_apex_keys_apk_certs_HandlesApkCertsSyntax(self):
    output_meta_dir = common.MakeTempDir()

    framework_meta_dir = common.MakeTempDir()
    os.symlink(
        os.path.join(self.testdata_dir, 'apkcerts_framework.txt'),
        os.path.join(framework_meta_dir, 'apkcerts.txt'))

    vendor_meta_dir = common.MakeTempDir()
    os.symlink(
        os.path.join(self.testdata_dir, 'apkcerts_vendor.txt'),
        os.path.join(vendor_meta_dir, 'apkcerts.txt'))

    merge_package_keys_txt(framework_meta_dir, vendor_meta_dir, output_meta_dir,
                           'apkcerts.txt')

    merged_entries = []
    merged_path = os.path.join(self.testdata_dir, 'apkcerts_merge.txt')

    with open(merged_path) as f:
      merged_entries = f.read().split('\n')

    output_entries = []
    output_path = os.path.join(output_meta_dir, 'apkcerts.txt')

    with open(output_path) as f:
      output_entries = f.read().split('\n')

    return self.assertEqual(merged_entries, output_entries)

  def test_item_list_to_partition_set(self):
    item_list = [
        'META/apexkeys.txt',
        'META/apkcerts.txt',
        'META/filesystem_config.txt',
        'PRODUCT/*',
        'SYSTEM/*',
        'SYSTEM_EXT/*',
    ]
    partition_set = item_list_to_partition_set(item_list)
    self.assertEqual(set(['product', 'system', 'system_ext']), partition_set)

  def test_compile_split_sepolicy(self):
    product_out_dir = common.MakeTempDir()

    def write_temp_file(path, data=''):
      full_path = os.path.join(product_out_dir, path)
      if not os.path.exists(os.path.dirname(full_path)):
        os.makedirs(os.path.dirname(full_path))
      with open(full_path, 'w') as f:
        f.write(data)

    write_temp_file(
        'system/etc/vintf/compatibility_matrix.device.xml', """
      <compatibility-matrix>
        <sepolicy>
          <kernel-sepolicy-version>30</kernel-sepolicy-version>
        </sepolicy>
      </compatibility-matrix>""")
    write_temp_file('vendor/etc/selinux/plat_sepolicy_vers.txt', '30.0')

    write_temp_file('system/etc/selinux/plat_sepolicy.cil')
    write_temp_file('system/etc/selinux/mapping/30.0.cil')
    write_temp_file('product/etc/selinux/mapping/30.0.cil')
    write_temp_file('vendor/etc/selinux/vendor_sepolicy.cil')
    write_temp_file('vendor/etc/selinux/plat_pub_versioned.cil')

    cmd = compile_split_sepolicy(product_out_dir, {
        'system': 'system',
        'product': 'product',
        'vendor': 'vendor',
    })
    self.assertEqual(' '.join(cmd),
                     ('secilc -m -M true -G -N -c 30 '
                      '-o {OTP}/META/combined_sepolicy -f /dev/null '
                      '{OTP}/system/etc/selinux/plat_sepolicy.cil '
                      '{OTP}/system/etc/selinux/mapping/30.0.cil '
                      '{OTP}/vendor/etc/selinux/vendor_sepolicy.cil '
                      '{OTP}/vendor/etc/selinux/plat_pub_versioned.cil '
                      '{OTP}/product/etc/selinux/mapping/30.0.cil').format(
                          OTP=product_out_dir))

  def _copy_apex(self, source, output_dir, partition):
    shutil.copy(
        source,
        os.path.join(output_dir, partition, 'apex', os.path.basename(source)))

  @test_utils.SkipIfExternalToolsUnavailable()
  def test_validate_merged_apex_info(self):
    output_dir = common.MakeTempDir()
    os.makedirs(os.path.join(output_dir, 'SYSTEM/apex'))
    os.makedirs(os.path.join(output_dir, 'VENDOR/apex'))

    self._copy_apex(
        os.path.join(self.testdata_dir, 'has_apk.apex'), output_dir, 'SYSTEM')
    self._copy_apex(
        os.path.join(test_utils.get_current_dir(),
                     'com.android.apex.compressed.v1.capex'), output_dir,
        'VENDOR')
    validate_merged_apex_info(output_dir, ('system', 'vendor'))

  @test_utils.SkipIfExternalToolsUnavailable()
  def test_validate_merged_apex_info_RaisesOnPackageInMultiplePartitions(self):
    output_dir = common.MakeTempDir()
    os.makedirs(os.path.join(output_dir, 'SYSTEM/apex'))
    os.makedirs(os.path.join(output_dir, 'VENDOR/apex'))

    same_apex_package = os.path.join(self.testdata_dir, 'has_apk.apex')
    self._copy_apex(same_apex_package, output_dir, 'SYSTEM')
    self._copy_apex(same_apex_package, output_dir, 'VENDOR')
    self.assertRaisesRegexp(
        common.ExternalError,
        'Duplicate APEX packages found in multiple partitions: com.android.wifi',
        validate_merged_apex_info, output_dir, ('system', 'vendor'))