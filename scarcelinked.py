#!/usr/bin/python3
# vim: tw=79
'''
Copyright © 2018 Endless Mobile, Inc.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''
import argparse
import collections
import difflib
import math
import os
import subprocess


Inode = collections.namedtuple('Inode', ('st_dev', 'st_ino'))
_Contents = collections.namedtuple('_Contents',
                                   ('inode_paths',   # Inode -> [path]
                                    'inode_sizes',   # Inode -> int
                                    'path_inodes'))  # path  -> Inode


class Contents(_Contents):
    def __new__(cls):
        return _Contents.__new__(cls, {}, {}, {})

    def sum_inode_size(self, inodes):
        return sum(self.inode_sizes[i] for i in inodes)


# spans: [(int, int)]: a list of half-open intervals of bytes which differ. In
#                      the case where one file is longer than the other, the
#                      interval for the difference is included.
# n_bytes: int: number of bytes which differ
# pct: float: percentage of bytes which differ, relative to the larger file
Diff = collections.namedtuple('Diff', ('spans', 'n_bytes', 'pct'))


def build(root):
    c = Contents()

    for dirpath, dirnames, filenames in os.walk(root):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            filerelpath = os.path.relpath(filepath, root)
            st = os.lstat(filepath)
            inode = Inode(st.st_dev, st.st_ino)

            c.inode_paths.setdefault(inode, []).append(filerelpath)
            c.inode_sizes[inode] = st.st_size
            c.path_inodes[filerelpath] = inode

    return c


def size_table(left, right, paths):
    table = [
        (
            p,
            left.inode_sizes[left.path_inodes[p]],
            right.inode_sizes[right.path_inodes[p]],
        )
        for p in paths
    ]
    table.sort(key=lambda t: max(t[1], t[2]))
    return table


def diff_tree(args):
    left = build(args.left)
    right = build(args.right)

    l = left.inode_sizes.keys()
    r = right.inode_sizes.keys()

    both = l & r
    l_only = l - r
    r_only = r - l

    def f(label, x, inodes):
        print('{label:7} {n:-6} files, {size:-10} bytes'.format(
            label=label,
            n=len(inodes),
            size=x.sum_inode_size(inodes)))

    f('Common:', left, both)
    f('Left:', left, l_only)
    f('Right:', right, r_only)

    left_distinct_paths = {
        p
        for k in l - r
        for p in left.inode_paths[k]
    }
    left_paths_missing_in_right = (
        left_distinct_paths - right.path_inodes.keys())
    distinct = (
        left_distinct_paths & right.path_inodes.keys())

    print('Only in {}: {}'.format(args.left, len(left_paths_missing_in_right)))
    if args.list_unique:
        for path in sorted(left_paths_missing_in_right):
            print('- {}'.format(path))
    print('Exist but different in both trees:', len(distinct))
    print('Worst offenders:')
    worst_offenders = size_table(left, right, distinct)[-25:]
    path_width = max(len(path) for path, *rest in worst_offenders)
    fmt = '| {:{}} | {:>9} | {:>9} | {:>9} |'
    print(fmt.format('Path', path_width, 'Left', 'Right', 'Diff'))
    print(fmt.format('----', path_width, '----', '-----', '----'))
    for path, s, t in worst_offenders:
        diff = diff_files(os.path.join(args.left, path),
                          os.path.join(args.right, path))
        print(fmt.format(path, path_width, s, t, diff.n_bytes))


def diff_bytes(left, right):
    '''This function is either very fast or very slow. If you're lucky you can
    guess which it'll be.

    TODO: early-return in the slow case where more than some threshold of the
    file is found to be different.'''

    def diff_span(i, k):
        if left[i:k] == right[i:k]:
            return []

        if k - i == 1:
            return [(i, k)]
        else:
            j = (i + k) // 2
            p = diff_span(i, j)
            q = diff_span(j, k)
            if p and q and p[-1][1] == q[0][0]:
                q[0] = (p[-1][0], q[0][1])
                del p[-1]

            return p + q
    n, m = sorted((len(left), len(right)))
    return diff_span(0, n) + ([] if n == m else [(n, m)])


def diff_files(left_path, right_path):
    with open(left_path, 'rb') as f:
        left = f.read()
    with open(right_path, 'rb') as f:
        right = f.read()

    spans = diff_bytes(left, right)
    n_bytes = sum(k - i for i, k in spans)
    pct = 100 * n_bytes / max(len(left), len(right))
    return Diff(spans, n_bytes, pct)


def hexdump_range(path, i, k):
    start = 512 * math.floor(i / 512)
    end = 512 * math.ceil(k / 512)
    length = end - start
    return subprocess.check_output((
        'hexdump', '-C', '-s', str(start), '-n', str(length),
        path,
    ), universal_newlines=True)


def blockwise_diff(args):
    '''For small files, diffoscope is better since it provides more information
    (eg it knows how to feed ELFs into readelf to label the differences).

    It seems unhappy with extremely large binaries so I wrote this.'''
    left_path = os.path.join(args.left, args.path)
    right_path = os.path.join(args.right, args.path)

    diff = diff_files(left_path, right_path)
    print('{} bytes ({:.4}%) differ'.format(diff.n_bytes, diff.pct))

    if diff.n_bytes <= args.diff_threshold:
        for i, k in diff.spans:
            left_hexdump = hexdump_range(left_path, i, k)
            right_hexdump = hexdump_range(right_path, i, k)
            for line in difflib.unified_diff(left_hexdump.splitlines(),
                                             right_hexdump.splitlines(),
                                             left_path,
                                             right_path,
                                             lineterm=''):
                print(line)


def main():
    '''Tools to compare trees of mostly-hardlinked files, such as two related
    Flatpak runtimes, to investigate whether as many files as you might hope
    are truly hardlinked together.'''
    p = argparse.ArgumentParser(description=main.__doc__)
    sp = p.add_subparsers(title='subcommands', dest='subcommand')
    sp.required = True

    dt = sp.add_parser('tree',
                       help='Compare the contents of two directory trees')
    dt.set_defaults(func=diff_tree)
    dt.add_argument('--list-unique', action='store_true',
                    help="List files which are only in left")
    dt.add_argument('left', help='path to a directory')
    dt.add_argument('right', help='path to a directory')

    bd = sp.add_parser('file',
                       help='Compare a specific file in the two trees',
                       epilog='This is very fast if left/path and right/path '
                              'are almost identical, and very slow if not.')
    bd.set_defaults(func=blockwise_diff)
    bd.add_argument('--diff-threshold', metavar='T', type=int, default=512,
                    help='if ≤ T bytes differ, print a diff (default: 512)')
    bd.add_argument('left', help='path to a directory')
    bd.add_argument('right', help='path to a directory')
    bd.add_argument('path', help='relative path to a file which exists in '
                                 'both left and right')

    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
