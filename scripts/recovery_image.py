"""Validate the immutable wheel-recovery region of a linked test image."""
import hashlib
import struct


def verify_recovery(image, build, checks=None):
    guard = build.get('reset_recovery')
    if not guard or not guard.get('before_c_runtime'):
        raise ValueError('Image has no reset-entry wheel recovery contract')
    start, end = guard['start'], guard['end']
    if not (8 <= start < guard['rom_entry'] < end < 0x3d000):
        raise ValueError('Recovery region is outside the qualified code range')
    if struct.unpack_from('<I', image, 4)[0] != (start | 1):
        raise ValueError('Reset vector bypasses wheel recovery')
    if hashlib.sha256(image[start:end]).hexdigest() != guard['sha256']:
        raise ValueError('Recovery code changed after the build')
    if 'hardfault_entry' in guard:
        entry = guard['hardfault_entry']
        if not start <= entry < end or struct.unpack_from('<I', image, 12)[0] != entry | 1:
            raise ValueError('HardFault vector bypasses the protected recovery handler')
    if checks is not None:
        tested = checks.get('reset_recovery', {})
        if not tested.get('before_c_runtime') or tested.get('protected_sha256') != guard['sha256']:
            raise ValueError('Reset-entry recovery has not passed the linked ARM checks')
        actual = {(c['wheel_held'], c['software_magic'], c['reached']) for c in tested.get('cases', [])}
        if actual != {(False, False, 'runtime'), (True, False, 'rom'),
                      (False, True, 'rom'), (True, True, 'rom')}:
            raise ValueError('Recovery checks do not cover both wheel states and software requests')
    return guard
