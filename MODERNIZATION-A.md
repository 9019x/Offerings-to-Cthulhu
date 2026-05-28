2026-05-27T01:53:03Z | FIRE START | model=claude-sonnet-4-6
2026-05-27T01:57:05Z | FIX .github/workflows/windows-build-depends.yml:88 | protoc not found; Qt GUI disabled | add DEPENDS_PREFIX/native/bin to PATH in configure step
2026-05-27T02:08:35Z | FIRE START | model=claude-sonnet-4-6
2026-05-27T02:08:48Z | WAITING for run 26486424518
2026-05-27T11:57:43Z | FIX rcc/uic Qt host tools missing | symlink from native/bin into expected qtbase/bin path before make
2026-05-27T12:23:50Z | FIX move Qt host tools symlink BEFORE autogen+configure (qmake runs in configure)
2026-05-27T13:22:19Z | FIX explicit --with-qt-incdir/libdir/plugindir/bindir to configure (QtCore headers missing warning)
2026-05-27T15:11:05Z | FIX add libpng to depends (Qt detects yes but PNG check fails; bundled qt-libpng not exposed as pkg-config)
2026-05-27T16:09:25Z | FIX add Qt plugin -L paths to LDFLAGS (platforms/accessible/imageformats/styles); libqwindows.a et al exist but were not on search path
2026-05-27T16:32:57Z | FIX skip qtaccessiblewidgets static plugin check for Qt5 (plugin removed in Qt5)
2026-05-27T16:55:37Z | FIX skip qwindows configure pre-check; just append -lqwindows to QT_LIBS so compile-time Q_IMPORT_PLUGIN works
2026-05-27T17:54:13Z | FIX qt -no-openssl -> -openssl-linked + OPENSSL_LIBS (paymentserver.cpp needs QSslError)
2026-05-27T18:09:40Z | FIRE START | model=claude-sonnet-4-6
2026-05-27T18:09:50Z | WAITING for run 26528881825
2026-05-27T18:13:34Z | FIX bump openssl 1.0.1k->1.0.2u + drop no-X flags (Qt 5.12 needs X509_STORE_CTX_get0_store)
2026-05-27T18:43:54Z | FIX remove Qt5 AccessibleFactory Q_IMPORT_PLUGIN + add Qt5*Support + Windows SDK libs to QT_LIBS for static plugin link
2026-05-27T19:08:56Z | FIRE START | model=claude-sonnet-4-6
2026-05-27T19:09:08Z | WAITING for run 26531470979
2026-05-27T20:09:18Z | FIRE START | model=claude-sonnet-4-6
2026-05-27T20:14:28Z | FIX src/m4/bitcoin_qt.m4:351 | undefined reference to hb_ot_tags_from_script (libQt5Gui harfbuzz-ng) | add AC_CHECK_LIB(qtharfbuzz) to static Qt5/Windows link block
2026-05-27T20:15:36Z | FIX src/m4/bitcoin_qt.m4:351 | undefined reference to hb_ot_tags_from_script (libQt5Gui harfbuzz-ng) | prepend -lqtharfbuzz to static Qt5/Windows QT_LIBS
2026-05-27T21:09:07Z | FIRE START | model=claude-sonnet-4-6
2026-05-27T21:09:33Z | WAITING for run 26538861465
2026-05-27T22:09:11Z | FIRE START | model=claude-sonnet-4-6
2026-05-27T22:12:07Z | WAITING for run 26541795121 (queued; triggered by merge of modernize-depends into main)
2026-05-27T23:09:14Z | FIRE START | model=claude-sonnet-4-6
2026-05-27T23:09:50Z | WAITING for run 26544111113
2026-05-28T00:13:16Z | FIRE START | model=claude-sonnet-4-6
2026-05-28T00:13:36Z | WAITING for run 26546385908
2026-05-28T18:09:29Z | FIRE START | model=claude-sonnet-4-6
2026-05-28T18:09:40Z | WAITING for run 26592408230
2026-05-28T19:09:06Z | FIRE START | model=claude-sonnet-4-6
