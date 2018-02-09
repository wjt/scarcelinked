Scarcelinked
============

Suppose you have two [Flatpak](https://flatpak.org/about.html) runtimes, `org.example.Base` and `com.example.Child`, where the latter is derived from the former. If you already have Child installed, you would hope that installing Base would be essentially free in terms of disk space thanks to the Magic of [OSTree](https://ostree.readthedocs.io/).

As you may have guessed from the name of this tool, this turned out not to be true in the case I was looking at, where Child was derived from a slightly older build of Base. Many files, including many multi-megabyte binaries, differed only in a handful of bytes, such as the `NT_GNU_BUILD_ID` string which is calculated from [many things in the build environment](https://blog.beuc.net/posts/Practical_basics_of_reproducible_builds/). The [Reproducible Builds](https://reproducible-builds.org/) people are shaking their heads in recognition.

Anyway, you might want a tool to diff trees of files like this, and to compare files within them. If so, this tool is great for the first use case, and acceptable for the second.

Example
-------

Compare two hardlink trees:

```console
$ ./scarcelinked.py tree \
> /var/lib/flatpak/runtime/org.gnome.Platform/x86_64/3.26/active/files \
> /var/lib/flatpak/runtime/com.endlessm.apps.Platform/x86_64/3/active/files
Common:  20066 files,  491004054 bytes
Left:      384 files,  145799433 bytes
Right:    6328 files,  264950271 bytes
Only in /var/lib/flatpak/runtime/org.gnome.Platform/x86_64/3.26/active/files: 7
Exist but different in both trees: 382
Worst offenders:
```

| Path                                        |      Left |     Right |      Diff |
| ----                                        |      ---- |     ----- |      ---- |
| lib/gstreamer-1.0/libgstrtpmanager.so       |    368752 |    368752 |        24 |
| lib/libvte-2.91.so.0.5000.1                 |    374824 |    374824 |        24 |
| lib/gstreamer-1.0/libgstcoreelements.so     |    381328 |    381328 |        23 |
| lib/libgstgl-1.0.so.0.1203.0                |    387968 |    387968 |        24 |
| lib/libgstbase-1.0.so.0.1203.0              |    407456 |    407456 |        24 |
[ … 16 lines omitted … ]
| lib/libgtk-3.so.0.2200.26                   |   7411328 |   7355560 |   6756349 |
| lib/libjavascriptcoregtk-4.0.so.18.6.15     |  16955248 |  16955248 |     60402 |
| libexec/webkit2gtk-4.0/WebKitPluginProcess2 |  38176776 |  38176776 |        24 |
| lib/libwebkit2gtk-4.0.so.37.24.9            |  43571640 |  43571640 |      3523 |

Weird! There's 146MB of stuff not shared between parent and child runtime, and many of those files are almost identical. Let's compare the contents of one file with identical size in both trees, which differs in only 24 bytes:

```console
$ ./scarcelinked.py file \
> /var/lib/flatpak/runtime/org.gnome.Platform/x86_64/3.26/active/files \
> /var/lib/flatpak/runtime/com.endlessm.apps.Platform/x86_64/3/active/files
> lib/gstreamer-1.0/libgstrtpmanager.so
24 bytes (0.006508%) differ
```

```diff
--- /var/lib/flatpak/runtime/org.gnome.Platform/x86_64/3.26/active/files/lib/gstreamer-1.0/libgstrtpmanager.so
+++ /var/lib/flatpak/runtime/com.endlessm.apps.Platform/x86_64/3/active/files/lib/gstreamer-1.0/libgstrtpmanager.so
@@ -27,7 +27,7 @@
 000001a0  e8 7d 25 00 00 00 00 00  e8 7d 25 00 00 00 00 00  |.}%......}%.....|
 000001b0  18 12 00 00 00 00 00 00  18 12 00 00 00 00 00 00  |................|
 000001c0  01 00 00 00 00 00 00 00  04 00 00 00 14 00 00 00  |................|
-000001d0  03 00 00 00 47 4e 55 00  f3 ca ac fd 78 1f a7 ce  |....GNU.....x...|
-000001e0  03 ca a5 76 8e 51 08 a1  25 98 04 8b 00 00 00 00  |...v.Q..%.......|
+000001d0  03 00 00 00 47 4e 55 00  c3 2d 04 8e b3 dc 99 f1  |....GNU..-......|
+000001e0  93 f4 83 1d 9d 8a ec b3  a9 df ea 2a 00 00 00 00  |...........*....|
 000001f0  02 00 00 00 ca 01 00 00  01 00 00 00 06 00 00 00  |................|
 00000200
--- /var/lib/flatpak/runtime/org.gnome.Platform/x86_64/3.26/active/files/lib/gstreamer-1.0/libgstrtpmanager.so
+++ /var/lib/flatpak/runtime/com.endlessm.apps.Platform/x86_64/3/active/files/lib/gstreamer-1.0/libgstrtpmanager.so
@@ -13,7 +13,7 @@
 000598c0  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
 *
 000598e0  6c 69 62 67 73 74 72 74  70 6d 61 6e 61 67 65 72  |libgstrtpmanager|
-000598f0  2e 73 6f 2e 64 65 62 75  67 00 00 00 25 1f 0a 75  |.so.debug...%..u|
+000598f0  2e 73 6f 2e 64 65 62 75  67 00 00 00 52 0c 0e 12  |.so.debug...R...|
 00059900  00 2e 64 61 74 61 00 2e  72 6f 64 61 74 61 00 2e  |..data..rodata..|
 00059910  73 68 73 74 72 74 61 62  00 2e 64 79 6e 61 6d 69  |shstrtab..dynami|
 00059920  63 00 2e 6e 6f 74 65 2e  67 6e 75 2e 62 75 69 6c  |c..note.gnu.buil|
```

If you were to feed these two files to [diffoscope](https://diffoscope.org/) you would learn that these differences are the `NT_GNU_BUILD_ID` (unique build ID bitstring) and some bytes in the `.gnu_debuglink` section.
