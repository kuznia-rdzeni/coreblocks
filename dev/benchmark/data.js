window.BENCHMARK_DATA = {
  "lastUpdate": 1689150648420,
  "repoUrl": "https://github.com/kuznia-rdzeni/coreblocks",
  "entries": {
    "Performance (IPC)": [
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f22d67ada17b425d5e4d759d9549404cd1a2d2a4",
          "message": "Hopefully fix benchmark workflow (#373)",
          "timestamp": "2023-06-01T11:43:07+02:00",
          "tree_id": "381ba085799084d3cb5e79c9863a83179d704f99",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/f22d67ada17b425d5e4d759d9549404cd1a2d2a4"
        },
        "date": 1685613584522,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f2bcf12703b8b37e301522bdef2d9da8627fe0e9",
          "message": "Make fetcher ready for discarding multiple instructions (#375)",
          "timestamp": "2023-06-02T23:12:01+02:00",
          "tree_id": "107554c4d5dadde6d00b56d1c13e7015404e70b5",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/f2bcf12703b8b37e301522bdef2d9da8627fe0e9"
        },
        "date": 1685741322498,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a903b181b1884403a2558d682777bf5dc6fb3651",
          "message": "Make verify_branch know its origin with from_pc (#378)",
          "timestamp": "2023-06-02T23:33:49+02:00",
          "tree_id": "41f8563314467cc9f70ec01ffd7ad94305b9b00d",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/a903b181b1884403a2558d682777bf5dc6fb3651"
        },
        "date": 1685742793637,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cf1004ef9628fc3b7d2020e4c39d409311436706",
          "message": "Instruction decoder refactor (#379)",
          "timestamp": "2023-06-05T09:01:09+02:00",
          "tree_id": "841173c625873d45aeb07cf431c66d70821f1dca",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/cf1004ef9628fc3b7d2020e4c39d409311436706"
        },
        "date": 1685949476490,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ebdabff1247eedb08004bd06dcd2c2eb7336d40a",
          "message": "Parametrize rs_entries in RSLayouts (#372)",
          "timestamp": "2023-06-05T09:17:07+02:00",
          "tree_id": "c1b76d3af644b6f5e9aedf358a9833853069bd95",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/ebdabff1247eedb08004bd06dcd2c2eb7336d40a"
        },
        "date": 1685950625929,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fd3857d23079b1e9c651e4b48381b361434228f8",
          "message": "ISA String improvements (#377)",
          "timestamp": "2023-06-05T11:31:11+02:00",
          "tree_id": "ec55139ad76e0945aca7c0d0ae9601c8a9b38261",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/fd3857d23079b1e9c651e4b48381b361434228f8"
        },
        "date": 1685959025883,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "pazeraf@gmail.com",
            "name": "Filip Pazera",
            "username": "pa000"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "92439af1cd33c528137d1824e57dcbc25cfecc71",
          "message": "Zbc functional unit (#294)",
          "timestamp": "2023-06-07T15:15:23+02:00",
          "tree_id": "b86c7b3dbdf4c1c28988f3374e5ae76d29224d48",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/92439af1cd33c528137d1824e57dcbc25cfecc71"
        },
        "date": 1686144913019,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "324526@uwr.edu.pl",
            "name": "Wojciech Pokój",
            "username": "wojpok"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c43c51454414b7acf25a52ea3b97af65e085294e",
          "message": "ZBB extension (#369)",
          "timestamp": "2023-06-12T10:55:42+02:00",
          "tree_id": "f017659bbe01efafb5fc6ba8c4e0d916649f22bf",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/c43c51454414b7acf25a52ea3b97af65e085294e"
        },
        "date": 1686561646127,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8381ebb9476f3205371010edfe2eba358a975fa3",
          "message": "Remove dummy sync signal (#387)",
          "timestamp": "2023-06-14T09:48:06+02:00",
          "tree_id": "255762b7705e9ff5723f58e8f4ba528b516234ac",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/8381ebb9476f3205371010edfe2eba358a975fa3"
        },
        "date": 1686729951150,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "63d824f90f451100f2d2de523bb66282d6834f1f",
          "message": "Update Amaranth version (#392)",
          "timestamp": "2023-06-19T13:22:33+02:00",
          "tree_id": "d4282f77208e706f1839a85208fcb9ff10b85a91",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/63d824f90f451100f2d2de523bb66282d6834f1f"
        },
        "date": 1687174811918,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "712601e17afd3aef891651487a454908f3399869",
          "message": "Simultaneous transactions (#347)",
          "timestamp": "2023-06-22T20:56:17+02:00",
          "tree_id": "a7daa806d0abe77635e1e1ff859f0392657ca161",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/712601e17afd3aef891651487a454908f3399869"
        },
        "date": 1687461256473,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f5302ce9d42c5fbaecd1bf1dbe32d6ab7bd4681c",
          "message": "Try-product combiner (#391)",
          "timestamp": "2023-06-23T13:03:54+02:00",
          "tree_id": "463106b8295841f359e500761e10b8e2df981e12",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/f5302ce9d42c5fbaecd1bf1dbe32d6ab7bd4681c"
        },
        "date": 1687519300371,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "95f038d1819ad9a919443dd7311cca6e42b34dd4",
          "message": "Layout for exceptions (#393)",
          "timestamp": "2023-06-23T15:19:34+02:00",
          "tree_id": "d6f0f7c2d315449290d80f7db682f939f5dc5518",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/95f038d1819ad9a919443dd7311cca6e42b34dd4"
        },
        "date": 1687527439068,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "324526@uwr.edu.pl",
            "name": "Wojciech Pokój",
            "username": "wojpok"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "75b1161f734c1be0ca8063d2b648defdb7cf1cfa",
          "message": "Encoding uniqueness (#388)",
          "timestamp": "2023-06-26T11:40:52+02:00",
          "tree_id": "1e6bf18541a503ca50c508443053e6fda5baaf4e",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/75b1161f734c1be0ca8063d2b648defdb7cf1cfa"
        },
        "date": 1687773541292,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "802d33498bdc94739ad6048dab2b696d15556012",
          "message": "Exception support (#386)",
          "timestamp": "2023-06-27T12:12:37+02:00",
          "tree_id": "8b6af11e6b5a4050a59bfbc9db2e32fa4ada6fec",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/802d33498bdc94739ad6048dab2b696d15556012"
        },
        "date": 1687861853076,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cc5cc1740a758a11b8485627453afa85bb633ce8",
          "message": "MemoryBank and Serializer (#304)",
          "timestamp": "2023-06-27T15:09:19+02:00",
          "tree_id": "9e0498ff5b040e236aac06dfdee35afacf6e68fe",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/cc5cc1740a758a11b8485627453afa85bb633ce8"
        },
        "date": 1687872469103,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "ud",
            "value": 0.29163741321475933,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.3753409431602963,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15128913530656055,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20042344550924895,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.3382389623347468,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28342665913210674,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24265409717186368,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21254611128189363,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f58fd958bde32881d6f8b40fc1c2e9039147022b",
          "message": "DummyLSU: Delay pushing store result until execution (#398)",
          "timestamp": "2023-06-28T12:21:39+02:00",
          "tree_id": "2d8b2665595b553e7b59752bd8b8bb050ce1532f",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/f58fd958bde32881d6f8b40fc1c2e9039147022b"
        },
        "date": 1687948789830,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "aha-mont64",
            "value": 0.28757457429729644,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.2950910250985018,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24334628411853151,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20199456436288493,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.2142909720634896,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.34326885628975723,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15129959734328294,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.383974924819342,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "24831d688ef84c9a22b1e1d28f9f2f6995faa0e7",
          "message": "Synthesize different core versions (#407)",
          "timestamp": "2023-06-30T19:16:15+02:00",
          "tree_id": "d1155c0f1fa5af0e559571c62e4e008b2e852372",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/24831d688ef84c9a22b1e1d28f9f2f6995faa0e7"
        },
        "date": 1688146538644,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "nettle-sha256",
            "value": 0.34326885628975723,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.2142909720634896,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20199456436288493,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28757457429729644,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24334628411853151,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.383974924819342,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.2950910250985018,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15129959734328294,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "02ade9b3b62130fd43613c133f0795f9b8b4e590",
          "message": "auto_debug_signals: drop useless empty objects (#418)",
          "timestamp": "2023-07-03T09:54:37+02:00",
          "tree_id": "0b617871cc95985f0d03f07726694063ce08bdff",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/02ade9b3b62130fd43613c133f0795f9b8b4e590"
        },
        "date": 1688371959393,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "minver",
            "value": 0.24334628411853151,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.2142909720634896,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.28757457429729644,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.34326885628975723,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15129959734328294,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20199456436288493,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.383974924819342,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.2950910250985018,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "324526@uwr.edu.pl",
            "name": "Wojciech Pokój",
            "username": "wojpok"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "de5279129166eed9b2311f9e9fa4fc3935466ac8",
          "message": "Division unit (#389)",
          "timestamp": "2023-07-03T11:38:04+02:00",
          "tree_id": "4080e1f3982cece53f160cbfa11a749aa94822bf",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/de5279129166eed9b2311f9e9fa4fc3935466ac8"
        },
        "date": 1688378207666,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "slre",
            "value": 0.21250038417801273,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.383974924819342,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.2828491744495354,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29335309567662415,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24125798497454903,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20126447714429588,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.36743626977565014,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.1537547475379883,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "98f5b887708e7b3cfa0456bc3b7f828b0488a602",
          "message": "Use Zbc and Zbs in full core (#421)",
          "timestamp": "2023-07-03T14:01:00+02:00",
          "tree_id": "bb2ab9d118ffffc4d31965d88232339329bf6fd3",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/98f5b887708e7b3cfa0456bc3b7f828b0488a602"
        },
        "date": 1688386901269,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "crc32",
            "value": 0.383974924819342,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.2828491744495354,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20126447714429588,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.36743626977565014,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29335309567662415,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.1537547475379883,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24125798497454903,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21250038417801273,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "18ec74480a04c0f89879ce6fe518c0b18dac7fd9",
          "message": "Fix isa string generation (#424)",
          "timestamp": "2023-07-03T15:04:01+02:00",
          "tree_id": "6390a018b0e22dfec7501a130e1b4a9ddd70313a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/18ec74480a04c0f89879ce6fe518c0b18dac7fd9"
        },
        "date": 1688390668537,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "nettle-sha256",
            "value": 0.36743626977565014,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21250038417801273,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.2828491744495354,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20126447714429588,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.383974924819342,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24125798497454903,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.1537547475379883,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29335309567662415,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1799f5e77fccd9077c4039bf4ba6a705e6cd9180",
          "message": "Make timeouts bigger (#426)",
          "timestamp": "2023-07-03T15:58:39+02:00",
          "tree_id": "be9b28f0453009cd382d4739f66d820023f17cce",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/1799f5e77fccd9077c4039bf4ba6a705e6cd9180"
        },
        "date": 1688393974383,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "statemate",
            "value": 0.20126447714429588,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.2828491744495354,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.1537547475379883,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21250038417801273,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24125798497454903,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.36743626977565014,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.383974924819342,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29335309567662415,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3e3b1715429501e341dd0dc12f6c66dbb63d8493",
          "message": "Exceptions implementation (#394)",
          "timestamp": "2023-07-03T16:09:24+02:00",
          "tree_id": "a46717caf38ffc8da1cb2d34b098039e39fd574d",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/3e3b1715429501e341dd0dc12f6c66dbb63d8493"
        },
        "date": 1688394677081,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "statemate",
            "value": 0.20126447714429588,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.383974924819342,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21250038417801273,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.2828491744495354,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.1537547475379883,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.36743626977565014,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29335309567662415,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24125798497454903,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6bf3b70c715c000e46e9eeedf1548bf566e0d831",
          "message": "Remove wiki deploy (#423)",
          "timestamp": "2023-07-03T16:20:17+02:00",
          "tree_id": "b28e80060e450568692689ddf53fba345b30ed20",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/6bf3b70c715c000e46e9eeedf1548bf566e0d831"
        },
        "date": 1688396136361,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "aha-mont64",
            "value": 0.2828491744495354,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.1537547475379883,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24125798497454903,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29335309567662415,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.383974924819342,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.20126447714429588,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.21250038417801273,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.36743626977565014,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "df6653bed7ab1e4a3331a76e9397ed4dc5b28f94",
          "message": "Simplified DummyLSU (#427)",
          "timestamp": "2023-07-05T10:04:45+02:00",
          "tree_id": "c868af0fb16744d8440a6fce02683d7588f791b4",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/df6653bed7ab1e4a3331a76e9397ed4dc5b28f94"
        },
        "date": 1688545553548,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "slre",
            "value": 0.2159196483640026,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.287102112304355,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.36868634053500093,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24225926200771405,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15476224925165344,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29403051593959734,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.21143582629957916,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.38400652367450455,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "263095dcd4f32c100231bad2f61ad269ee653712",
          "message": "Single caller method check (#425)",
          "timestamp": "2023-07-05T11:13:41+02:00",
          "tree_id": "8ab0e869c67c6969b51db2e35075bd24b0181d5a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/263095dcd4f32c100231bad2f61ad269ee653712"
        },
        "date": 1688549748809,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "minver",
            "value": 0.24225926200771405,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.36868634053500093,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.2159196483640026,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.38400652367450455,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.287102112304355,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29403051593959734,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.21143582629957916,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15476224925165344,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "654117c1c76a892627dc4734f6cc2936e0f03975",
          "message": "Change default value for nonblocking (#415)",
          "timestamp": "2023-07-08T11:13:35+02:00",
          "tree_id": "703e7f5dd32f81f783b04c54685789404979f600",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/654117c1c76a892627dc4734f6cc2936e0f03975"
        },
        "date": 1688808894386,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "minver",
            "value": 0.24225926200771405,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.36868634053500093,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15476224925165344,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29403051593959734,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.287102112304355,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.38400652367450455,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.2159196483640026,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.21143582629957916,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "Kristopher38@wp.pl",
            "name": "Krzysztof Obłonczek",
            "username": "Kristopher38"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6344da745a97aa22bec2c6dad67357c97e001494",
          "message": "Use all available cores when compiling cocotb regression tests with verilator (#430)",
          "timestamp": "2023-07-10T12:07:24+02:00",
          "tree_id": "493a60b72edba7b70036367f533ccb07467a123d",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/6344da745a97aa22bec2c6dad67357c97e001494"
        },
        "date": 1688984902164,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "statemate",
            "value": 0.21143582629957916,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.287102112304355,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15476224925165344,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.36868634053500093,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24225926200771405,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.2159196483640026,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29403051593959734,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.38400652367450455,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fcba37657d00309fee22f63d45d1341918d2012d",
          "message": "Improve GenericFunctionalTestUnit (#433)",
          "timestamp": "2023-07-11T21:34:19+02:00",
          "tree_id": "49a81cd4b9dd011c1b4bbca5396dc832e1a49845",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/fcba37657d00309fee22f63d45d1341918d2012d"
        },
        "date": 1689105601750,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "statemate",
            "value": 0.21143582629957916,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29403051593959734,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.38400652367450455,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24225926200771405,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.2159196483640026,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15476224925165344,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.36868634053500093,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.287102112304355,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "de07d43dd31e5b05c361c0cb6825431e92992d8f",
          "message": "Method run debugging (#432)",
          "timestamp": "2023-07-11T21:53:54+02:00",
          "tree_id": "5e737f38d73ab2d7ee421e1315b8fd563a8278c4",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/de07d43dd31e5b05c361c0cb6825431e92992d8f"
        },
        "date": 1689106500890,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "ud",
            "value": 0.29403051593959734,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.38400652367450455,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.36868634053500093,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15476224925165344,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.21143582629957916,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "slre",
            "value": 0.2159196483640026,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.287102112304355,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24225926200771405,
            "unit": "Instructions Per Cycle"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5bf55b86d82d6fb4f4e163c33754466c993e4224",
          "message": "DummyLSU: add FENCE (#441)",
          "timestamp": "2023-07-12T10:10:13+02:00",
          "tree_id": "8bc43b04a38aa1a8e2bf0e1e4364af706bc91af9",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/5bf55b86d82d6fb4f4e163c33754466c993e4224"
        },
        "date": 1689150646898,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "slre",
            "value": 0.2159196483640026,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nettle-sha256",
            "value": 0.36868634053500093,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "statemate",
            "value": 0.21143582629957916,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "ud",
            "value": 0.29403051593959734,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "crc32",
            "value": 0.38400652367450455,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "aha-mont64",
            "value": 0.287102112304355,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "nsichneu",
            "value": 0.15476224925165344,
            "unit": "Instructions Per Cycle"
          },
          {
            "name": "minver",
            "value": 0.24225926200771405,
            "unit": "Instructions Per Cycle"
          }
        ]
      }
    ],
    "Fmax and LCs (basic)": [
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "759a5c0183898735e822d5ef21b2329ada3972bf",
          "message": "Fix benchmark action (#153)",
          "timestamp": "2022-12-20T10:16:57+01:00",
          "tree_id": "56f7bc67518500a127701fdb3cef1b12193cc295",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/759a5c0183898735e822d5ef21b2329ada3972bf"
        },
        "date": 1671528092957,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 65.11,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 11143,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 140,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 536,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 2934,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "050a8a4ede452b1b638071691d0c7fbf386dc371",
          "message": "Add more info about the development environment (#147)",
          "timestamp": "2022-12-20T10:26:30+01:00",
          "tree_id": "41056a5231e02149cc44b6517feecec9d4ba5875",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/050a8a4ede452b1b638071691d0c7fbf386dc371"
        },
        "date": 1671528669214,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.51,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 11328,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 172,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 536,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 2934,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "58303687+wkkuna@users.noreply.github.com",
            "name": "wkkuna",
            "username": "wkkuna"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0390803058a6e11ef51d884977dc77ce562ccb97",
          "message": "[#146] Add script for building docs locally (#148)",
          "timestamp": "2022-12-21T19:00:58+01:00",
          "tree_id": "fec4f29426897a61daeb5f2f8e9cce1edb2634f7",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/0390803058a6e11ef51d884977dc77ce562ccb97"
        },
        "date": 1671645928455,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 63.4,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 11257,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 140,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 536,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 2934,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4ab7ab1f070703207b85dade3e744d047ea4823c",
          "message": "Automatic debug signals (#145)",
          "timestamp": "2022-12-21T19:03:01+01:00",
          "tree_id": "8cd26b097f215e08eb2a042513782a09307c32b8",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/4ab7ab1f070703207b85dade3e744d047ea4823c"
        },
        "date": 1671645988680,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 65.11,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 11143,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 140,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 536,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 2934,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "27aaf002eb3a5b680a4b18066f2b6676e5689dd0",
          "message": "Nonexclusive methods (#140)",
          "timestamp": "2022-12-21T19:05:27+01:00",
          "tree_id": "df15f1b82e40f78369f0473ce28375962771588e",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/27aaf002eb3a5b680a4b18066f2b6676e5689dd0"
        },
        "date": 1671646231519,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.51,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 11328,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 172,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 536,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 2934,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8b18ec1bbb237700b19c191d5e518b8d0997bdc4",
          "message": "Assign for ArrayProxy (#152)",
          "timestamp": "2022-12-23T21:02:16+01:00",
          "tree_id": "fb117ed78c83f6c618165c27e8a6913aba96c24c",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/8b18ec1bbb237700b19c191d5e518b8d0997bdc4"
        },
        "date": 1671825981569,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 64.63,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 11143,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 140,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 536,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 2934,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fe51503947a9cf86e39eaf4cc9e6741516aedbe6",
          "message": "Document benchmarks page (#159)",
          "timestamp": "2022-12-24T10:40:30+01:00",
          "tree_id": "3a7ecc91b967262cd5cbaa53ada484ec165dac49",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/fe51503947a9cf86e39eaf4cc9e6741516aedbe6"
        },
        "date": 1671875028072,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 65.11,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 11143,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 140,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 536,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 2934,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "pkaras.it@gmail.com",
            "name": "Phoenix Himself",
            "username": "Ph0enixKM"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5ce7ecf2993a586eba19689b2a41706d157c9269",
          "message": "feat: add logo (#158)",
          "timestamp": "2022-12-24T10:43:35+01:00",
          "tree_id": "7311b16ddc57de839c69340ee7a4598b9cf56646",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/5ce7ecf2993a586eba19689b2a41706d157c9269"
        },
        "date": 1671875258094,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 65.11,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 11143,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 140,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 536,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 2934,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4d3e731e3a6b0994a0271b3c1c535ed9b899ba57",
          "message": "Remove free_rf fifo adapter from synthesis (#161)",
          "timestamp": "2022-12-26T15:59:31+01:00",
          "tree_id": "8ba31a9101cf1f730458f154e0ceab249ebf20d4",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/4d3e731e3a6b0994a0271b3c1c535ed9b899ba57"
        },
        "date": 1672067034643,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 59.35,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 15170,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 540,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4669,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7c981bd87f4ea3b380baeedb78edf144999a1fe2",
          "message": "Fix repository pinning (#160)",
          "timestamp": "2022-12-31T11:13:59+01:00",
          "tree_id": "1672962105cca5783a22b4fa2026fdc732d16a57",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/7c981bd87f4ea3b380baeedb78edf144999a1fe2"
        },
        "date": 1672481908908,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.48,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 15170,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 540,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4669,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "db7bfc0f0b5ce26b6e38ac7f9f4d7a57d404c20c",
          "message": "Added check for existence of common field in assign (#163)",
          "timestamp": "2023-01-02T13:54:27+01:00",
          "tree_id": "2d48212a1280794e0bc06370f7a3739a97a53ef8",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/db7bfc0f0b5ce26b6e38ac7f9f4d7a57d404c20c"
        },
        "date": 1672664329243,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 61.13,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14784,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 540,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4669,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7883603a9fbc109044627d4181ee70ffff292471",
          "message": "Verify PEP8 naming (#169)",
          "timestamp": "2023-01-03T00:09:54+01:00",
          "tree_id": "8d6f364b588e03c83c8aed031a0ce798e7cd5651",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/7883603a9fbc109044627d4181ee70ffff292471"
        },
        "date": 1672701248241,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 60.16,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14784,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 540,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4669,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c5561ea3e91de6e31cc216f4cabfbdf80d1ca31a",
          "message": "Refactor of TestbenchIO for more intuitive method mocking (#138)",
          "timestamp": "2023-01-03T14:40:28+01:00",
          "tree_id": "baf33e42b413d4c699f61a6810c153d67d51c8fa",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/c5561ea3e91de6e31cc216f4cabfbdf80d1ca31a"
        },
        "date": 1672753570091,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 63.54,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14784,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 540,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4669,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "565e55824a663c86a792e66639ef168fa0593dc1",
          "message": "Add workflow_dispatch to benchmark.yml (#167)",
          "timestamp": "2023-01-03T14:43:21+01:00",
          "tree_id": "12f203c2b1ae1e3a1d5cf6a817031f3d63d43520",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/565e55824a663c86a792e66639ef168fa0593dc1"
        },
        "date": 1672753657963,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 60.16,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14784,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 540,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4669,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "bd350a696343e8fe138a34012f80a2438508a12c",
          "message": "Add Method.proxy() (#164)",
          "timestamp": "2023-01-04T21:52:40+01:00",
          "tree_id": "aafd49c044a2244a7cd619ea79b5b25b0e5dc847",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/bd350a696343e8fe138a34012f80a2438508a12c"
        },
        "date": 1672865865701,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.12,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14740,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 180,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 540,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4669,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c5a555495c248a3ca195d4a7176a3a807fbacbb4",
          "message": "Actions: bump actions/setup-python to v4 (#178)",
          "timestamp": "2023-01-05T21:40:39+01:00",
          "tree_id": "8b5a05f76c3a00b9ff5e719a0d6f711c6677e1bf",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/c5a555495c248a3ca195d4a7176a3a807fbacbb4"
        },
        "date": 1672951646907,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 65.39,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14740,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 180,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 540,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4669,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "edd9e7dba1930d066e9b9dcca6a1235571a2ae3a",
          "message": "Reduce synthesis Docker image size (#168)",
          "timestamp": "2023-01-05T21:43:12+01:00",
          "tree_id": "a5b377adee42538e68fc9df186eab03719fcc9ad",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/edd9e7dba1930d066e9b9dcca6a1235571a2ae3a"
        },
        "date": 1672951661589,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 61.13,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14784,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 540,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4669,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9ae01461379f81d5718a2befb1566edb97ec01de",
          "message": "Add a mermaid graph to the docs build (#170)",
          "timestamp": "2023-01-06T10:47:39+01:00",
          "tree_id": "696668ece073fa072e6f7efbae9533766c3294fa",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/9ae01461379f81d5718a2befb1566edb97ec01de"
        },
        "date": 1672998673114,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.48,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 15170,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 540,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4669,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c87bb3112a437e47afae65752e7efcd9035054d9",
          "message": "Unify common transaction and method functionality (#175)",
          "timestamp": "2023-01-08T18:15:21+01:00",
          "tree_id": "89e42952803cab64eb9c213a09498ba827d84b06",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/c87bb3112a437e47afae65752e7efcd9035054d9"
        },
        "date": 1673198384951,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.48,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 15170,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 540,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4669,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "933f296e37a0fcfe2716d4ea62f539a2de785ebc",
          "message": "Add decorator for method_handler_loop (#157)",
          "timestamp": "2023-01-10T13:27:24+01:00",
          "tree_id": "d29e212d932bf2ab270e015c2682109b5c33b5b6",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/933f296e37a0fcfe2716d4ea62f539a2de785ebc"
        },
        "date": 1673353941785,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 61.13,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14784,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 540,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4669,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "Kristopher38@wp.pl",
            "name": "Kristopher38",
            "username": "Kristopher38"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "128312add363ad5fc393bd3ec2bd31010041a082",
          "message": "Branch detection and resolution (#139)",
          "timestamp": "2023-01-10T20:00:00+01:00",
          "tree_id": "26287ed3ce5928971c59c9bb7096486bbb6db2a2",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/128312add363ad5fc393bd3ec2bd31010041a082"
        },
        "date": 1673377473171,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.77,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 13872,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 180,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4670,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "marekbauer07@gmail.com",
            "name": "Marek Bauer",
            "username": "speederking07"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ffd899b5b500b5cba9d70b1dbfc1fe56a881bffb",
          "message": "Added missing extension for RISC-V ISA (#182)",
          "timestamp": "2023-01-11T11:30:59+01:00",
          "tree_id": "8ef1159ce5ae70c468451e9f5def7c0ba75c0cc7",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/ffd899b5b500b5cba9d70b1dbfc1fe56a881bffb"
        },
        "date": 1673433321163,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.77,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 13872,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 180,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4670,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "56a390da8de363d0da082e24675713eb7934e939",
          "message": "auto-graph: base edge directions on data flow (#171)",
          "timestamp": "2023-01-11T15:55:06+01:00",
          "tree_id": "7fc4b2f208877c24b8c174163b7c292ff6f929a6",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/56a390da8de363d0da082e24675713eb7934e939"
        },
        "date": 1673449198012,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 61.15,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14900,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4670,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "bf75a16a1f6e614d54fdd09e5d64c055a3d25233",
          "message": "Change synthesis Docker image (#184)",
          "timestamp": "2023-01-11T16:02:16+01:00",
          "tree_id": "9526f06dd4bdf7b806ebaf798e644def85abf98f",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/bf75a16a1f6e614d54fdd09e5d64c055a3d25233"
        },
        "date": 1673449691645,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.77,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 13872,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 180,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4670,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "33c87c100a4ede936ba88fc279ab1240e3e8dc29",
          "message": "Improvement to ELK graph output (#174)",
          "timestamp": "2023-01-11T18:14:46+01:00",
          "tree_id": "83636f20c0adf8987f950db60f69f67b395f4ab9",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/33c87c100a4ede936ba88fc279ab1240e3e8dc29"
        },
        "date": 1673457607411,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 61.15,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14900,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4670,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "194b396b7634f5288930d277a2762843954712a6",
          "message": "Improve stubs for Amaranth (#179)",
          "timestamp": "2023-01-11T18:17:14+01:00",
          "tree_id": "43a08dfed1743cde90f9d4b719c4cf4a8efd0ed0",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/194b396b7634f5288930d277a2762843954712a6"
        },
        "date": 1673457721671,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 61.15,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14900,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 148,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4670,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3fbf8b959ff384450c44e03f554fb6b4b9e851b3",
          "message": "Fix BasicFifo (#177)",
          "timestamp": "2023-01-11T20:27:44+01:00",
          "tree_id": "3765ab856cb9b4fced594d260aa390f8b196d633",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/3fbf8b959ff384450c44e03f554fb6b4b9e851b3"
        },
        "date": 1673465512197,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.33,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14010,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 158,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4671,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "63b88b8d891fd74dd1cd4941fccbacf222f551bd",
          "message": "Refactor of functional units (#165)",
          "timestamp": "2023-01-11T23:53:38+01:00",
          "tree_id": "f8f32a49ea400a64f33bd6b2ae566107c4cbb648",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/63b88b8d891fd74dd1cd4941fccbacf222f551bd"
        },
        "date": 1673477914971,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.52,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 13847,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 158,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4671,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "84f1ead5b0373c7e6d1f552613ac435bdb5f4a90",
          "message": "Hoisting combinatorial assignments from transaction and method bodies (#176)",
          "timestamp": "2023-01-13T11:23:23+01:00",
          "tree_id": "a3aaeab14a4a3c63ebc92d0a894afa42eb68b8ed",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/84f1ead5b0373c7e6d1f552613ac435bdb5f4a90"
        },
        "date": 1673605714115,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 61.26,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 13724,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 158,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4671,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c38d3347bc19a1aaa11b6433963aeac04ecd74ef",
          "message": "Multiple FU per RS (#181)",
          "timestamp": "2023-01-13T11:38:50+01:00",
          "tree_id": "2e29ea85a0f819add51d9ac0b76d6978f97f1c0f",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/c38d3347bc19a1aaa11b6433963aeac04ecd74ef"
        },
        "date": 1673606572363,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 61.7,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 13602,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 242,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 608,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4744,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "84439b2a9f8dfbc70c83ccad913913be061062ba",
          "message": "Dummy LSU - Loads and stores (#123)",
          "timestamp": "2023-01-15T17:07:21+01:00",
          "tree_id": "2bddb7af8f1b071bf4c305d4c3951585e8961b0b",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/84439b2a9f8dfbc70c83ccad913913be061062ba"
        },
        "date": 1673799108673,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 60.79,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14198,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 242,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 608,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4744,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6dd52e66ab57c17005d30b485efc67a326fae60e",
          "message": "Forwarding module (#187)",
          "timestamp": "2023-01-16T10:26:36+01:00",
          "tree_id": "f449cfbb80232ca215d55e42df043282d4365b1b",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/6dd52e66ab57c17005d30b485efc67a326fae60e"
        },
        "date": 1673861494958,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 63.25,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 14075,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 242,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4786,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "196906a42c1d25b879298b0a4c2c6c4441cb1e23",
          "message": "Set PYTHONHASHSEED=0 on generating core (#192)",
          "timestamp": "2023-01-16T17:29:11+01:00",
          "tree_id": "3abb02abbf4bee30d54b8086ca707c5205eb0a69",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/196906a42c1d25b879298b0a4c2c6c4441cb1e23"
        },
        "date": 1673886820353,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.92,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 13775,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 210,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4786,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "edd9e317b6994af2844ca3298a76486731af446b",
          "message": "Hoist read_value computation out of Forwarder read method (#195)",
          "timestamp": "2023-01-18T10:36:28+01:00",
          "tree_id": "2c5246b069a1e4272c8e6dddd20da2a46c299abb",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/edd9e317b6994af2844ca3298a76486731af446b"
        },
        "date": 1674034813943,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 60.99,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 13710,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 242,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4786,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fecc38d3ce1a2b21ab656d745a0896b2032c73cc",
          "message": "Fix dummylsu methods (#193)",
          "timestamp": "2023-01-18T10:39:25+01:00",
          "tree_id": "c87ff32517ce43bc2d6076909f18665db7cff47a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/fecc38d3ce1a2b21ab656d745a0896b2032c73cc"
        },
        "date": 1674035061069,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 60.99,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 13710,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 242,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4786,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "marekbauer07@gmail.com",
            "name": "Marek Bauer",
            "username": "speederking07"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "03a9268ba585271e1d52817e03a034f1fe4f0df8",
          "message": "Multiple RS support (#190)",
          "timestamp": "2023-01-23T00:27:46+01:00",
          "tree_id": "06a71804f0c3f4fd1cae0a3be469e04a795fa285",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/03a9268ba585271e1d52817e03a034f1fe4f0df8"
        },
        "date": 1674430308149,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 61.82,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 13944,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 242,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4907,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5d3b511e853313eb7fb3eabbb61f2b6f0beae5dc",
          "message": "Remove unneeded backticks (#211)",
          "timestamp": "2023-01-25T13:35:29+01:00",
          "tree_id": "e866b256a61d7e9abb3a5dbb09e871e1f873b928",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/5d3b511e853313eb7fb3eabbb61f2b6f0beae5dc"
        },
        "date": 1674650402757,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 61.82,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 13944,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 242,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 560,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 4907,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "Kristopher38@wp.pl",
            "name": "Kristopher38",
            "username": "Kristopher38"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "91e54a59771966f729cb01c9c42d337aadf25039",
          "message": "Branch support (#188)\n\nMerging.",
          "timestamp": "2023-01-25T21:42:36+01:00",
          "tree_id": "454029bd32a8eb4dbd8c6d2b5a35ab33570627a4",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/91e54a59771966f729cb01c9c42d337aadf25039"
        },
        "date": 1674679910705,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.07,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16079,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 420,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5076,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "27353092469c1d9d36644b6e71390c53abb1054d",
          "message": "Initial README (#203)",
          "timestamp": "2023-01-26T09:11:43+01:00",
          "tree_id": "4777ac984018af63da298276a901719329a069bd",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/27353092469c1d9d36644b6e71390c53abb1054d"
        },
        "date": 1674721118013,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.07,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16079,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 420,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5076,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9df1f1f9287ed8da9325eaafb9c151ee0af43df0",
          "message": "Bump Amaranth version to latest master (#218)\n\nNeeded for #194\n\nCo-authored-by: KrosFire <hubik080@gmail.com>",
          "timestamp": "2023-01-29T20:04:01+01:00",
          "tree_id": "b97022276c3cd0d64d3df0b1acb827437ba43d0c",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/9df1f1f9287ed8da9325eaafb9c151ee0af43df0"
        },
        "date": 1675019336081,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 53.58,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16540,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 420,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5076,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "13ef881e305ed869142a9213910381838b95384d",
          "message": "More useful automatic debug signals (#210)",
          "timestamp": "2023-01-30T23:11:41+01:00",
          "tree_id": "605dd9f2df89f1e0f77bdd9725ea17e558abc1a6",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/13ef881e305ed869142a9213910381838b95384d"
        },
        "date": 1675116977410,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 53.58,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16540,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 420,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5076,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ce99e7cbdaaadce5e59d127581c15a1b15251b88",
          "message": "Pipelined Wishbone Master (#185)",
          "timestamp": "2023-01-31T11:14:20+01:00",
          "tree_id": "587561f7c1e8dcdf3713ff74112f45d9b0c6ccf2",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/ce99e7cbdaaadce5e59d127581c15a1b15251b88"
        },
        "date": 1675160410218,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 52.41,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16916,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 420,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5076,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "marekbauer07@gmail.com",
            "name": "Marek Bauer",
            "username": "speederking07"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9fd5b494598e728dce52176e390a8bfe09ab71c4",
          "message": "Docstrings for scheduler (#206)",
          "timestamp": "2023-02-01T14:45:48+01:00",
          "tree_id": "18e43ed8fed0409fc646476ce9dc2084dd6399c3",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/9fd5b494598e728dce52176e390a8bfe09ab71c4"
        },
        "date": 1675259605425,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 52.41,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16916,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 420,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5076,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "18d264e5f6c4565497cdc03428ae159201a0a3c8",
          "message": "Document `core_graph` and `build-docs.sh`. (#215)",
          "timestamp": "2023-02-01T21:40:10+01:00",
          "tree_id": "b3ccb9ff6e9a6b759593ee7c6a7b0fbb719347b8",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/18d264e5f6c4565497cdc03428ae159201a0a3c8"
        },
        "date": 1675284449619,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 52.41,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16916,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 420,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5076,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9faa17bea993112ccb1c35b33b5becfec18a620a",
          "message": "Remove int method layouts (#221)",
          "timestamp": "2023-02-03T09:22:28+01:00",
          "tree_id": "180d306b94a7501fe6261e1fdfc484a4afef8ed0",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/9faa17bea993112ccb1c35b33b5becfec18a620a"
        },
        "date": 1675412889747,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.63,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16314,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 452,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5076,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "82132828b953d35895adedfe85f5aee4c1229f35",
          "message": "LSU support (#213)",
          "timestamp": "2023-02-03T11:41:36+01:00",
          "tree_id": "b21536d5dbc09d43be4c4cb900baf951e67d36e8",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/82132828b953d35895adedfe85f5aee4c1229f35"
        },
        "date": 1675421214003,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.58,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17889,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 478,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5447,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "hubik080@gmail.com",
            "name": "Hubert Jabłoński",
            "username": "KrosFire"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e536f66272747081487984021af04fa3222a0dd0",
          "message": "Zbs (#194)",
          "timestamp": "2023-02-04T18:19:17+01:00",
          "tree_id": "63f0bd20cae2e5c2db37f91fc6b2c25069f7e20a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/e536f66272747081487984021af04fa3222a0dd0"
        },
        "date": 1675531620471,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.28,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17250,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 510,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5447,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "269e6474c64796ff25ebe252a5f45e6aa70ede25",
          "message": "Kwargs in method calls (#225)",
          "timestamp": "2023-02-06T21:55:49+01:00",
          "tree_id": "bd0f28ee4bea46fdde96467e903ced1ce7db4a7b",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/269e6474c64796ff25ebe252a5f45e6aa70ede25"
        },
        "date": 1675717464404,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.28,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17250,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 510,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5447,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "de7ac0b367564d59885ac252f2916a9f14d407d1",
          "message": "Remove int layout from docstrings (#226)",
          "timestamp": "2023-02-07T14:13:16+01:00",
          "tree_id": "27696ad40d07861951ddc64df94065b8906e0f5e",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/de7ac0b367564d59885ac252f2916a9f14d407d1"
        },
        "date": 1675775962269,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.28,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17250,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 510,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5447,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8d26ed0df5ee38ad4c03316ed6d37861f2ac952d",
          "message": "Make Collector a method combinator (#227)",
          "timestamp": "2023-02-09T19:52:46+01:00",
          "tree_id": "2bbb08ac4fe5699d8dada98ce43b5184690874c9",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/8d26ed0df5ee38ad4c03316ed6d37861f2ac952d"
        },
        "date": 1675969242968,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.28,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17250,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 510,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5447,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f5216a26ceaee564b856d59f75e4d37313372a2e",
          "message": "Use assign in transaction core (#222)",
          "timestamp": "2023-02-18T13:00:33+01:00",
          "tree_id": "4baded1139d61b467fb6aa96db9a99d797a8033f",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/f5216a26ceaee564b856d59f75e4d37313372a2e"
        },
        "date": 1676722010184,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 60.72,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17586,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 512,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "645c790ffd8792d562e5a330785f843fea07c033",
          "message": "Avoid duplicating IDs in graphs (#229)",
          "timestamp": "2023-02-25T19:03:42+01:00",
          "tree_id": "2801448fea977747fa60afe62d276092de43c671",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/645c790ffd8792d562e5a330785f843fea07c033"
        },
        "date": 1677348547544,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.45,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17694,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 512,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ffd4bfe860766ca12c8290daaea4404a216868c9",
          "message": "Mention `assign` in problem checklist (#233)",
          "timestamp": "2023-02-26T20:08:28+01:00",
          "tree_id": "09be9c7bea2f0b8347fa325bd6e513e8b8ed2051",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/ffd4bfe860766ca12c8290daaea4404a216868c9"
        },
        "date": 1677438834700,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.45,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17694,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 512,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3b776e82e439e29d3c923a3d988876d04bfb902c",
          "message": "Fixes and improvements to Amaranth type stubs (#201)",
          "timestamp": "2023-02-27T11:29:43+01:00",
          "tree_id": "e1392591908d532b21ff7142a5cd678270486877",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/3b776e82e439e29d3c923a3d988876d04bfb902c"
        },
        "date": 1677494160072,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 60.72,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17586,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 512,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2d97a49af470a302b7a5983d4c6f3cbdf6979c44",
          "message": "Argument syntax for def_method (#212)",
          "timestamp": "2023-02-27T12:26:01+01:00",
          "tree_id": "120a07e4b482009fa747bb287831b1a65152682a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/2d97a49af470a302b7a5983d4c6f3cbdf6979c44"
        },
        "date": 1677497511012,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 60.72,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17586,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 512,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2d91cea9bb959eec5c1bcd9b743d55e54766a8e6",
          "message": "Allow different layouts for RS units (#228)",
          "timestamp": "2023-03-05T18:37:56+01:00",
          "tree_id": "e1455345a099aa4abf3969f42cfe165d36634cdc",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/2d91cea9bb959eec5c1bcd9b743d55e54766a8e6"
        },
        "date": 1678038217509,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.32,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17509,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 512,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7b069f564bafffcda470e70e90439be11cc26ef4",
          "message": "Updated amaranth version, due to dropping support by pip for old syntax (#234)",
          "timestamp": "2023-03-09T11:12:31+01:00",
          "tree_id": "4bf5a87b11c3152587724ddd2ad8f05a26a6ca24",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/7b069f564bafffcda470e70e90439be11cc26ef4"
        },
        "date": 1678357092268,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.77,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17149,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 512,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "marekbauer07@gmail.com",
            "name": "Marek Bauer",
            "username": "speederking07"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "27640d962f38b51bb920135a4889de901679bc1f",
          "message": "Configurable FU used by `GenParams` (#209)\n\nCo-authored-by: Marek Materzok <tilk@tilk.eu>\r\nCo-authored-by: Lekcyjna <309016@uwr.edu.pl>",
          "timestamp": "2023-03-13T14:32:43+01:00",
          "tree_id": "eb75ecb02f7e4943fca56c26009665ffe8e33737",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/27640d962f38b51bb920135a4889de901679bc1f"
        },
        "date": 1678718668955,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 53.8,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 26929,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 512,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 9454,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ce7cfb53f43a18b7c59a31f0df17488e2d13d82d",
          "message": "Fix the core_graph script after merging #209, and other cleanups (#245)",
          "timestamp": "2023-03-15T10:04:54+01:00",
          "tree_id": "d639b4ccece54c190692d9c9469bf2f8a2726f3c",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/ce7cfb53f43a18b7c59a31f0df17488e2d13d82d"
        },
        "date": 1678871475368,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.63,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17461,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 480,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1f5064a3f796015e2425e597220b2f6f63745afe",
          "message": "Make Sphinx CI fail on errors and warnings (#241)",
          "timestamp": "2023-03-15T10:07:21+01:00",
          "tree_id": "8f0fdf9ec0c88770ca066c3e386ed10237ef6726",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/1f5064a3f796015e2425e597220b2f6f63745afe"
        },
        "date": 1678871609186,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.63,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17461,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 480,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "692eae3c58c0bce50bf9aa1923d279fff442e58b",
          "message": "Move from dockerhub to GitHub Container Registry (#249)",
          "timestamp": "2023-03-16T20:17:13+01:00",
          "tree_id": "f921814c9ea87dae5213e3f037513b4b1ec3a703",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/692eae3c58c0bce50bf9aa1923d279fff442e58b"
        },
        "date": 1678994753734,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.63,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17461,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 480,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "52bacbc5eacf0f96a66d850dfbeba6db03a24a12",
          "message": "Lint scripts (#250)",
          "timestamp": "2023-03-17T16:41:42+01:00",
          "tree_id": "c0a58c2ced986c9b100f3e4302a447023af1ca73",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/52bacbc5eacf0f96a66d850dfbeba6db03a24a12"
        },
        "date": 1679068103661,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.63,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17461,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 480,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1eb458fbf062a6b7e818c94ff313a9f154ebd542",
          "message": "Zicsr extension - Unit and Register (#217)",
          "timestamp": "2023-03-17T17:37:51+01:00",
          "tree_id": "83e17dcab43cbdd4c5f5691c9c46a80edda64f67",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/1eb458fbf062a6b7e818c94ff313a9f154ebd542"
        },
        "date": 1679071375901,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.47,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16887,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 480,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 844,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fa6ec8da8237a5c04a1fc15baacd846a40e4db45",
          "message": "Add comments to `Priority` enum. (#255)",
          "timestamp": "2023-03-18T12:21:31+01:00",
          "tree_id": "fd042fd285efedc306d85add5d2c41770e689fc8",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/fa6ec8da8237a5c04a1fc15baacd846a40e4db45"
        },
        "date": 1679138816385,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.47,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16887,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 480,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 844,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "324526@uwr.edu.pl",
            "name": "Wojciech Pokój",
            "username": "wojpok"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a6debdf446a68aa7efaeaec6ebebf2ee741f77b8",
          "message": "ZBA extension built into ALU (#246)",
          "timestamp": "2023-03-18T20:05:51+01:00",
          "tree_id": "93348c7bda3921df21e837655b947ba18afbb0df",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/a6debdf446a68aa7efaeaec6ebebf2ee741f77b8"
        },
        "date": 1679166745633,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.95,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17040,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 572,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 844,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0ef5877a591048024461d1290a43638bcbc2f3b9",
          "message": "Add a script exporting the core to Verilog (#248)",
          "timestamp": "2023-03-20T20:09:07+01:00",
          "tree_id": "c4346132863bb772ecdf7d95d112c9d075ab97f9",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/0ef5877a591048024461d1290a43638bcbc2f3b9"
        },
        "date": 1679339617771,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.95,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17040,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 572,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 844,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "b7246785b4437cee50a515437ddafb9eeff4b823",
          "message": "TestbenchIO: new syntax suggestion for calls (#189)",
          "timestamp": "2023-03-21T23:11:08+01:00",
          "tree_id": "3422dc0ca26b6f08971803f8ae564adfa0a4f558",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/b7246785b4437cee50a515437ddafb9eeff4b823"
        },
        "date": 1679436936385,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.95,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17040,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 572,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 844,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "142e051a64e1d551958a9996db9e9dd87d56c9ad",
          "message": "Enums enums enums (#259)",
          "timestamp": "2023-03-24T13:51:42+01:00",
          "tree_id": "935efcc0ee111d0cc5642e6412361eb5e1fda13b",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/142e051a64e1d551958a9996db9e9dd87d56c9ad"
        },
        "date": 1679662597746,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.95,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17040,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 572,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 844,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0dd727476aed82e11282e692c78ac7c85a55327f",
          "message": "Added overview of publications about exceptions (#244)",
          "timestamp": "2023-03-24T18:01:54+01:00",
          "tree_id": "ef1b8ebf33acc026c3bd32e740b60b31aafb46bc",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/0dd727476aed82e11282e692c78ac7c85a55327f"
        },
        "date": 1679677573599,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.95,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17040,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 572,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 844,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2e3a79278ec3dd9aaf7897f88b2575f23c974498",
          "message": "Stubs for amaranth.lib.data (#239)",
          "timestamp": "2023-03-26T11:42:27+02:00",
          "tree_id": "52599815db8b62e4666b72d183e27c861652a039",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/2e3a79278ec3dd9aaf7897f88b2575f23c974498"
        },
        "date": 1679824034651,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.95,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17040,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 572,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 844,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "60522807b49f4d45dacfaccbb211933a484ca3a7",
          "message": "Support amaranth.lib.data structures in assign (#240)",
          "timestamp": "2023-03-26T11:46:20+02:00",
          "tree_id": "3e27146837df8ea3fd636df7dd582dbdef6f4112",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/60522807b49f4d45dacfaccbb211933a484ca3a7"
        },
        "date": 1679824237601,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.95,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17040,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 572,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 844,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5453,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0ab2e70f8d6a2b9f937e2ec1cb976d9f44a48bec",
          "message": "Wishbone connected to pins for synthesis benchmark (#251)",
          "timestamp": "2023-03-26T11:56:02+02:00",
          "tree_id": "fbd5e59134a89780c8412cd04a284b085548cd86",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/0ab2e70f8d6a2b9f937e2ec1cb976d9f44a48bec"
        },
        "date": 1679824952871,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.75,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18038,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 514,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5419,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cedb043b33d853710da8b2654dcccb9d7caa9be7",
          "message": "Abstract away implementation of Wishbone master (#256)",
          "timestamp": "2023-03-29T13:14:43+02:00",
          "tree_id": "f9773df79d747b8e0fac7726ed58b1fa9ae82d8c",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/cedb043b33d853710da8b2654dcccb9d7caa9be7"
        },
        "date": 1680089067735,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.32,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16774,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 546,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5419,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "pazeraf@gmail.com",
            "name": "Filip Pazera",
            "username": "pa000"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "797c39c706eb52ebfd3af79790b136ddd6bab368",
          "message": "Replace setattr on m.submodules by indexing (#270)",
          "timestamp": "2023-03-31T00:18:42+02:00",
          "tree_id": "cf8858a32732ac1f91507ed8fc611ef0fac46249",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/797c39c706eb52ebfd3af79790b136ddd6bab368"
        },
        "date": 1680215228796,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.32,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16774,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 546,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5419,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8af289276091d0671577ea16c16bf00123c8bfc6",
          "message": "New syntax for method mocks (#263)",
          "timestamp": "2023-03-31T13:35:50+02:00",
          "tree_id": "56e62ceed8e5b581dcc7940dab7dfe0771a1529e",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/8af289276091d0671577ea16c16bf00123c8bfc6"
        },
        "date": 1680262986614,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.32,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16774,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 546,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5419,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0fa8efa56437518aca035ac31df8d5ff1b193b60",
          "message": "Class method alternative approach (#272)",
          "timestamp": "2023-04-02T14:49:49+02:00",
          "tree_id": "b38b141cf14f9ff0387e2964dc7a96021a5a99f2",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/0fa8efa56437518aca035ac31df8d5ff1b193b60"
        },
        "date": 1680440346507,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.32,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16774,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 546,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5419,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9cd91072e67fa1470d37aefad842446f275837ba",
          "message": "DependencyManager: ListKey, key locking (#273)",
          "timestamp": "2023-04-03T18:07:40+02:00",
          "tree_id": "13f921a1f695efb9e793a0ebbd4c6eb21546f9ff",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/9cd91072e67fa1470d37aefad842446f275837ba"
        },
        "date": 1680538584375,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.32,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16774,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 546,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5419,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3b0b7f352c66b3fef1d82ddd37c18f2f0126cc99",
          "message": "Make 'enable' parameter in the method mock a lambda (#265)",
          "timestamp": "2023-04-03T19:19:36+02:00",
          "tree_id": "58422764106c49c6970c026fd098f2cd649b453b",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/3b0b7f352c66b3fef1d82ddd37c18f2f0126cc99"
        },
        "date": 1680542804961,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.32,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16774,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 546,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5419,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "77c8fee1d6932331dfb175d84235eabade2cea21",
          "message": "Refactor dependency management and fu config (#277)\n\n* Move DependencyManager to `dependencies.py`\n\n* Dataclass all the (*Params) things!\n\n* Remove questionable `from __future__`\n\n* Apply suggestion from CR",
          "timestamp": "2023-04-05T17:35:59+02:00",
          "tree_id": "4d3318f96662e0d00b367e16051065848618990e",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/77c8fee1d6932331dfb175d84235eabade2cea21"
        },
        "date": 1680709377528,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.32,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16774,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 546,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5419,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8eeab9323d6ee663bc312aef11c83889e8c2890f",
          "message": "Core generation configurations (#275)",
          "timestamp": "2023-04-06T20:55:50+02:00",
          "tree_id": "507757f811c1a64fe0f6d1369aee40b5245bb621",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/8eeab9323d6ee663bc312aef11c83889e8c2890f"
        },
        "date": 1680807739942,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.55,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17299,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 546,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5419,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "af7af4e3d93c4c2d90d80400366e2a1e61e67f57",
          "message": "Bump linter versions (#274)",
          "timestamp": "2023-04-07T15:14:52+02:00",
          "tree_id": "bc145773c6c1b3af07a244bde8a61b186bf3bc01",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/af7af4e3d93c4c2d90d80400366e2a1e61e67f57"
        },
        "date": 1680873687906,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.55,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17299,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 546,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5419,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "b5fadd3b15834016c2fe303f2aee5d3d53a08bbc",
          "message": "Add a function aligning numbers and a function for yielding for many cycles (#278)",
          "timestamp": "2023-04-09T11:47:29+02:00",
          "tree_id": "379784fe878b92712aefa9042896cf671aa195d2",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/b5fadd3b15834016c2fe303f2aee5d3d53a08bbc"
        },
        "date": 1681034021603,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.55,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17299,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 546,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5419,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "93173421c3596a95c3f5be06612af6992c75521c",
          "message": "Fix FreeRF FIFO initialization (#279)",
          "timestamp": "2023-04-09T11:50:38+02:00",
          "tree_id": "97d07be27d77fe4ebba4f6553d0acc8e82f875e3",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/93173421c3596a95c3f5be06612af6992c75521c"
        },
        "date": 1681034289930,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.53,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16757,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 520,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5425,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3ea750ed026994e63afa1a1f90ebd728e3c22b49",
          "message": "Instruction Cache 🚀 (#258)",
          "timestamp": "2023-04-10T11:01:33+02:00",
          "tree_id": "cc0df20ddf10991da3a691f69d9909160e07efb8",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/3ea750ed026994e63afa1a1f90ebd728e3c22b49"
        },
        "date": 1681117672485,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.78,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16823,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 520,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5425,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f05680d1844270bc494129b17ac0839f129950b6",
          "message": "Decoder fix for shift immediate handling (#284)\n\n* Decoder fix\n\n* Handle imm sign in decoder test, add regression check\n\n* Lint fix",
          "timestamp": "2023-04-10T14:40:00+02:00",
          "tree_id": "0273f30ec1c79ec78ea0806a167f284cae845448",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/f05680d1844270bc494129b17ac0839f129950b6"
        },
        "date": 1681130787161,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.18,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18634,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 520,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5425,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "db4ea83a8c2bfbd591eb839f0d0e4c9ad9f21277",
          "message": "LSU addressing fix (#283)\n\n* Fix LSU address breakage\n\n* LSU test fix\n\n* Fix lint and comment",
          "timestamp": "2023-04-10T14:43:16+02:00",
          "tree_id": "02c033337047be0738974ecb90085b2b234e03f9",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/db4ea83a8c2bfbd591eb839f0d0e4c9ad9f21277"
        },
        "date": 1681131110451,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.83,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 19112,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 554,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5433,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6e47c87fde4aa247d8d862c36ffbaea817ca0da2",
          "message": "Decoder: set invalid registers to 0 and fix CSR decoding (#282)\n\n* Mux reg_l to 0 if not valid and remove reg_v from layouts\n\n* Add missing docs\n\n* Fix tests\n\n* Always check r*_v field in decoder tests\n\n* Fix CSR decoding: split to CSR_REG and CSR_IMM\n\n* CSR unit optimization and test fix\n\n---------\n\nCo-authored-by: Marek Materzok <tilk@tilk.eu>",
          "timestamp": "2023-04-10T14:53:05+02:00",
          "tree_id": "126d4e62ed4d9ce36293634f3b2cad34f0322e9c",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/6e47c87fde4aa247d8d862c36ffbaea817ca0da2"
        },
        "date": 1681131535938,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.46,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17769,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 522,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5433,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "186cd181bfbbb4951b31635caf9a72c70853eaf7",
          "message": "Cocotb support (#268)\n\n* cocotb initial commit\n\n* Cocotb action\n\nLint\n\n* Fix requirements file\n\n* Add libpython3.10 to dockerfile\n\n* Build riscv-tests\n\n* Towards running tests\n\n* Wishbone handling\n\n* Add timeouts\n\n* Report test results\n\nLinting, exclude test from typechecking\n\n* Towards ELF support\n\n* Towards running tests\n\n* WiP: switch to icarus\n\n* Link instructions at address 0\n\n* Install iverilog in CI\n\n* Handle synchronous resetting\n\n* Replace prints with debug messages\n\n* Fix weird cases when memsz=0 but there is data\n\nFix\n\n* Support memory writes\n\n* Fix deprecation warning\n\n* Exclude external from tests\n\n* Remove Verilator stuff (for now)\n\n* Keep the container (for simplicity)\n\nWrong workflow changed\n\n* Exclude tests which will not pass currently\n\n* Fix lint after merge\n\n* Change memory delay to 0\n\n* Fix typo\n\n* Rename stuff in workflow\n\n* Remove sim time printing (it's done at the end anyway)",
          "timestamp": "2023-04-15T14:35:26+02:00",
          "tree_id": "68f489d230d767275e3706941d010ba8f48f1313",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/186cd181bfbbb4951b31635caf9a72c70853eaf7"
        },
        "date": 1681562493419,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.46,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17769,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 522,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5433,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6e9cad87045017a44a1eca5eb26356d9e94ec6af",
          "message": "CSR integration and improvements (#267)\n\n* params: add list dependency key\n\n* csr: Use CSRListKey dependency for registering CSRs\n\n* csr: apply FU BlockComponent to CSR unit + fetch\n\n* rob: add single_entry signal\n\n* csr: bind fetch_continue method to get_result execution\n\n* csr: add csr_generic file: csr addresses, priv and combined csrs spec\n\n* retirement: implement insret csr\n\n* csr: Check privilege level and read-only bits from csr address in unit\n\n* docs: fix docstrings\n\n* Fetch: stall fetch on SYSTEM opcode\n\n* scheduler: fix missing `csr` field\n\n* csr: doublecounter docstrings + regs rename\n\n* core-test: generalize asm test runner and add simple csr asm test\n\n* csr+key: detect if registers are added after unit elaboration\n\n* params: add list dependency key\n\n* params: add dependency_exists\n\n* params: add key locking\n\n* params: rename dependency_exists to key_exists\n\n* params: add empty_valid parameter to key\n\n* params: set empty_valid=True in ListKey\n\n* Implement cycle and time, add comment\n\n* Address review comments\n\n* Fixes after merge\n\n* Add full core config to gen_verilog\n\nNote: Zmmul extension is not yet ratifed(?) and not available in compilers\n\n* Increase test time due to free_rf init\n\n* Address CR comments\n\n* Use Switch to match opcodes\n\n---------\n\nCo-authored-by: Marek Materzok <tilk@tilk.eu>",
          "timestamp": "2023-04-15T15:59:43+02:00",
          "tree_id": "4cf185ca9a6afdfa8e25db3b61915957e3c4f17a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/6e9cad87045017a44a1eca5eb26356d9e94ec6af"
        },
        "date": 1681567476181,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.04,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17617,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 554,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5433,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f5cedc664c7c7eaaf097461caf70cd2591dd1cf2",
          "message": "Proxy fix (#292)",
          "timestamp": "2023-04-18T17:38:24+02:00",
          "tree_id": "bb3aa909afa95d2812cd664729e4974ff550e63d",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/f5cedc664c7c7eaaf097461caf70cd2591dd1cf2"
        },
        "date": 1681832721167,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 59.26,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18227,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 554,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5433,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "69d6b2362810ac933728f998b3ef1ca057d0ec93",
          "message": "Add multiplication tests (#291)",
          "timestamp": "2023-04-18T17:48:49+02:00",
          "tree_id": "64bb416c78bdf23375ea96f0f31d886601611c3c",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/69d6b2362810ac933728f998b3ef1ca057d0ec93"
        },
        "date": 1681833356589,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 59.26,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18227,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 554,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5433,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "324526@uwr.edu.pl",
            "name": "Wojciech Pokój",
            "username": "wojpok"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "012a68a79a8b13b7cdded16a553e5cb2b96a36f1",
          "message": "Proof of concept instruction decoding (#257)",
          "timestamp": "2023-04-20T11:31:32+02:00",
          "tree_id": "42bed2502f90e2a121af50e458071bbff3956dd3",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/012a68a79a8b13b7cdded16a553e5cb2b96a36f1"
        },
        "date": 1681983612356,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 60.82,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18000,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 522,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5433,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5511f8871a22a4910af5ccfb3c0213b9ff96e8f5",
          "message": "Add a sanity check for ordered method definitions (#281)",
          "timestamp": "2023-04-23T09:42:04+02:00",
          "tree_id": "c94752603b47a3313eb7fec3b7a4063e1c9a070e",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/5511f8871a22a4910af5ccfb3c0213b9ff96e8f5"
        },
        "date": 1682236170602,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.58,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17999,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 522,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5433,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ec6abd09f25b4af8e69fe1cdf4fe74894b650306",
          "message": "Added timeouts for workflows. (#302)",
          "timestamp": "2023-04-23T19:11:46+02:00",
          "tree_id": "863ebc73ae415a0fcc068e36e3954d634b94d9a9",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/ec6abd09f25b4af8e69fe1cdf4fe74894b650306"
        },
        "date": 1682270507540,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.58,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17999,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 522,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5433,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "180dd538d0cc3f4043fb7c4a64c7ce3902289852",
          "message": "Fix Verilator on cocotb (#305)",
          "timestamp": "2023-04-25T11:40:08+02:00",
          "tree_id": "da0997bd895a56052e882aba4dd8899468476041",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/180dd538d0cc3f4043fb7c4a64c7ce3902289852"
        },
        "date": 1682416148222,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.58,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17999,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 522,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5433,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4b7200b2442af76245c77ab906232163c7c3307f",
          "message": "Transaction core refactor (#308)",
          "timestamp": "2023-04-27T12:11:14+02:00",
          "tree_id": "c19b3f3bb497863024a1755da300ac0de4e7d082",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/4b7200b2442af76245c77ab906232163c7c3307f"
        },
        "date": 1682590678575,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.58,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17999,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 522,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5433,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a7956318b8eff02c130b33842be49d5e3af76452",
          "message": "Add instruction cache bypass (#307)",
          "timestamp": "2023-04-27T12:16:15+02:00",
          "tree_id": "282795b3c8edbf5bf9a4db8e97c55f5a07335c3a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/a7956318b8eff02c130b33842be49d5e3af76452"
        },
        "date": 1682591046036,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.58,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17999,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 522,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 780,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5433,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e8de2415133d87f398992eb70c54d045d7a03702",
          "message": "Make the fetch unit use instruction cache (#271)",
          "timestamp": "2023-04-27T15:43:22+02:00",
          "tree_id": "5268e012793d93f02edc850be15128ee3a3757d0",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/e8de2415133d87f398992eb70c54d045d7a03702"
        },
        "date": 1682603433732,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.56,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18252,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ffde79fcdc6305e5562d8c1d9e908bb7fede2dea",
          "message": "RS debug signals (#303)",
          "timestamp": "2023-04-27T15:49:41+02:00",
          "tree_id": "59717c119b1a3215380f48051dd522baebc865c7",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/ffde79fcdc6305e5562d8c1d9e908bb7fede2dea"
        },
        "date": 1682603933985,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.56,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18252,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "Kristopher38@wp.pl",
            "name": "Krzysztof Obłonczek",
            "username": "Kristopher38"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "98fd23ad5ba70013180be1228a3d61848fcafd19",
          "message": "Run workflows of feature branches (#315)",
          "timestamp": "2023-04-29T13:30:50+02:00",
          "tree_id": "c809802bba20eb0e204c7de4a0683a0ea801e6cf",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/98fd23ad5ba70013180be1228a3d61848fcafd19"
        },
        "date": 1682768308314,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.56,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18252,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8f45c7b32de33e8b71c0ea0eae288789e340e3df",
          "message": "Module connector (#317)",
          "timestamp": "2023-05-02T12:41:51+02:00",
          "tree_id": "83218d9069a429fd54ca454a5d5829672bc07671",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/8f45c7b32de33e8b71c0ea0eae288789e340e3df"
        },
        "date": 1683024644288,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.56,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18252,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "96cbc4a3068953dec3caf4669efff16bcf8a0036",
          "message": "Refactor of ROB test. (#318)",
          "timestamp": "2023-05-02T13:58:47+02:00",
          "tree_id": "12bad880d11404ac585d3cb3a57d9b1cfbbab107",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/96cbc4a3068953dec3caf4669efff16bcf8a0036"
        },
        "date": 1683029142795,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.56,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18252,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "pazeraf@gmail.com",
            "name": "Filip Pazera",
            "username": "pa000"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9a23b060811d6c272ac20ca58878681a98966432",
          "message": "Fix graph (update requirements-dev.txt) (#323)",
          "timestamp": "2023-05-02T17:06:07+02:00",
          "tree_id": "500072381ab25bed8577f23d5bc6544b45c3672c",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/9a23b060811d6c272ac20ca58878681a98966432"
        },
        "date": 1683040381976,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.56,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18252,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "055790d85f49ff5c8b8dbe49dcacea400f2e1e1d",
          "message": "Fix `schedule_before` (#324)",
          "timestamp": "2023-05-03T14:15:00+02:00",
          "tree_id": "4240b6c223e1f8144989ad97cc348dfe41e88515",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/055790d85f49ff5c8b8dbe49dcacea400f2e1e1d"
        },
        "date": 1683116564953,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.45,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17945,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f30d53f3bb054240f04eeb541b2483ab5f194e42",
          "message": "Nestable transactions (#276)",
          "timestamp": "2023-05-03T15:17:53+02:00",
          "tree_id": "182daeae9644a6974e81bc39652256aa75946123",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/f30d53f3bb054240f04eeb541b2483ab5f194e42"
        },
        "date": 1683120259527,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.45,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17945,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8b14bc3a801bf0bc86f00ee98728a5afa4a1a386",
          "message": "Remove anonymous submodules (#314)",
          "timestamp": "2023-05-03T17:51:25+02:00",
          "tree_id": "61be75aaaca7bccdb2d495ef9d17238156c647fd",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/8b14bc3a801bf0bc86f00ee98728a5afa4a1a386"
        },
        "date": 1683129597927,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 52.24,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17648,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c09faa0442d36e69f9e8122d8fb2ac7f03c45203",
          "message": "Refactor tests with TransactionModule (#319)",
          "timestamp": "2023-05-06T11:01:52+02:00",
          "tree_id": "3d0d5c1a8a498c5d29a50cfbd4a5e59fbf7cf126",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/c09faa0442d36e69f9e8122d8fb2ac7f03c45203"
        },
        "date": 1683364317386,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.1,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18754,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0a6b0f310c0739f86cd2da58d5d145a3e1c016ab",
          "message": "Refactor method filter test (#321)",
          "timestamp": "2023-05-06T17:32:45+02:00",
          "tree_id": "7c86f1fad57ee7dbae6de91482c6a68510a3c9d9",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/0a6b0f310c0739f86cd2da58d5d145a3e1c016ab"
        },
        "date": 1683387636186,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.1,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18754,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4000f2fe8c5c6d36e00f20fe1e45033dee8b2b8a",
          "message": "Fix pushing CI docs (#330)",
          "timestamp": "2023-05-08T10:27:34+02:00",
          "tree_id": "7685b98bb2e6a05dab4233477539333e47020191",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/4000f2fe8c5c6d36e00f20fe1e45033dee8b2b8a"
        },
        "date": 1683534941476,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.1,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18754,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fb4d2a2b3b169ada65de841e13c3e408737c24d3",
          "message": "Fix wiki deploy (#332)",
          "timestamp": "2023-05-08T17:11:48+02:00",
          "tree_id": "16415777110fd3e4cd060426495af02ce2a9bc2c",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/fb4d2a2b3b169ada65de841e13c3e408737c24d3"
        },
        "date": 1683559171650,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.1,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18754,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e95f7a962aa054c93e4a447d7aaae6df9ab1816a",
          "message": "Optype refactor (#334)\n\n* Clean up optype stuff\n\n* Derive from protocols for early checking\n\n* Fixed test (avoid noqa please...)\n\n* Cleanup",
          "timestamp": "2023-05-11T17:11:30+02:00",
          "tree_id": "425eb5f08de7a3c37a076f4f440214e7f441cc8c",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/e95f7a962aa054c93e4a447d7aaae6df9ab1816a"
        },
        "date": 1683818358088,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.1,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18754,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "324526@uwr.edu.pl",
            "name": "Wojciech Pokój",
            "username": "wojpok"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "626d6c065f4b82d7b1b0c8ef05c0f32a5fd07f1b",
          "message": "ZBA enable flag (#333)",
          "timestamp": "2023-05-13T19:02:58+02:00",
          "tree_id": "5776efcf7de33d15c3fa464fcd2703c8c136dd21",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/626d6c065f4b82d7b1b0c8ef05c0f32a5fd07f1b"
        },
        "date": 1683997810541,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.1,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18754,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "b925ebb960d040fd261912c73b0777f76c58bd06",
          "message": "Fix debug_signals method bug introduced in #334 (#339)\n\n* Fix debug_signals method bug introduced in #334\n\n* lint\n\n---------\n\nCo-authored-by: Lekcyjna <309016@uwr.edu.pl>",
          "timestamp": "2023-05-14T20:23:39+02:00",
          "tree_id": "87b5f734f493c32d713f261442bf5f665bd7278b",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/b925ebb960d040fd261912c73b0777f76c58bd06"
        },
        "date": 1684089164894,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.1,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18754,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "18adb721b2e3652e1b341b79605add203077879e",
          "message": "Added new test to workflow to check if traces works. (#316)",
          "timestamp": "2023-05-16T12:31:21+02:00",
          "tree_id": "d0d6dfcd4103c15dd5c214774fd0be29cbbed4bd",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/18adb721b2e3652e1b341b79605add203077879e"
        },
        "date": 1684233502207,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.1,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 18754,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 562,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c7a0dd8e203223e6480f24038edef83cfc9348d4",
          "message": "Generate isa_str from func units config (#306)",
          "timestamp": "2023-05-17T17:04:30+02:00",
          "tree_id": "f64d625cb1855befe0a4c03c1f8ef48502faed38",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/c7a0dd8e203223e6480f24038edef83cfc9348d4"
        },
        "date": 1684336225027,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.63,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16954,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "739b1235c73230725fece3d27ad05c0203da942b",
          "message": "Fix method_uses (#336)",
          "timestamp": "2023-05-17T17:47:48+02:00",
          "tree_id": "4e49d55c47f96919ceaac8dd7c191635d79fef3b",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/739b1235c73230725fece3d27ad05c0203da942b"
        },
        "date": 1684338862889,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.41,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17253,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "26aaaa72f45f3d11b3c775708691fbfd3f82e30d",
          "message": "Auto debug signals from list (#269)",
          "timestamp": "2023-05-19T16:22:34+02:00",
          "tree_id": "233121b818ddc2dba478a3bfb07eef12805797f8",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/26aaaa72f45f3d11b3c775708691fbfd3f82e30d"
        },
        "date": 1684506578184,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.41,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17253,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9838d22409b6601efa75cac8df2af55dac426ac1",
          "message": "One-hot implementation change (#345)",
          "timestamp": "2023-05-21T10:47:59+02:00",
          "tree_id": "f51e8d9fb81bcd9b5d23e20eea4fdd877adef05a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/9838d22409b6601efa75cac8df2af55dac426ac1"
        },
        "date": 1684659529037,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 59.25,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17167,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 438,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "529ad2fc02006d18356bc08941712a2604931d61",
          "message": "Fix typo in test/common.py (#350)",
          "timestamp": "2023-05-21T12:46:11+02:00",
          "tree_id": "4dbb1b542265cd2a32cdacdc9e677a8384ad403f",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/529ad2fc02006d18356bc08941712a2604931d61"
        },
        "date": 1684666487396,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 59.25,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17167,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 438,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3862e721d4f696f4269b06b1c725f48b6f00e3c6",
          "message": "Method argument passing optimization (#346)",
          "timestamp": "2023-05-22T12:26:06+02:00",
          "tree_id": "497743197d057fd7abd8c11aa91fec1e8f9edf8a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/3862e721d4f696f4269b06b1c725f48b6f00e3c6"
        },
        "date": 1684751674657,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 60.08,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17852,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "26c26f778f6e0edd1277519f5cd5c2d2eb1fdcae",
          "message": "Add Dockerfile for RISCV toolchain (#349)",
          "timestamp": "2023-05-23T11:47:37+02:00",
          "tree_id": "4d3aafd63641a721c6a8811cabe6e7415c4e8e7b",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/26c26f778f6e0edd1277519f5cd5c2d2eb1fdcae"
        },
        "date": 1684835720302,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 60.08,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17852,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 812,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5604,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "324526@uwr.edu.pl",
            "name": "Wojciech Pokój",
            "username": "wojpok"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6a3bb92d0a35a1c09e8e229e0a92a86abdfa65c0",
          "message": "Shift Alu (#340)",
          "timestamp": "2023-05-23T12:59:43+02:00",
          "tree_id": "ea62086f131d17e70c5ed424e3f580de59445fe1",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/6a3bb92d0a35a1c09e8e229e0a92a86abdfa65c0"
        },
        "date": 1684840151082,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.49,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22781,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "d9499f87cb474d549461c31cb785bb2f38fb75c6",
          "message": "Refactor cocotb tests (#335)",
          "timestamp": "2023-05-24T09:35:12+02:00",
          "tree_id": "31fbb68800a7d01f0f63c5b2b08cd1ce79f50af1",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/d9499f87cb474d549461c31cb785bb2f38fb75c6"
        },
        "date": 1684914451270,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.49,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22781,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "acbd241b02e9e02480ff86c8ef6bac8a640f520d",
          "message": "Yet another debug log fix. (#353)",
          "timestamp": "2023-05-24T14:19:50+02:00",
          "tree_id": "2e167c469b675b84ce277997135865ad0f345c53",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/acbd241b02e9e02480ff86c8ef6bac8a640f520d"
        },
        "date": 1684931268387,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.49,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22781,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "43571100192f9d3aaa7d48ba29f0b5f7fddc3038",
          "message": "Popcount (#354)\n\nCo-authored-by: Lekcyjna <309016@uwr.edu.pl>\r\nCo-authored-by: Marek Materzok <tilk@tilk.eu>",
          "timestamp": "2023-05-24T23:50:07+02:00",
          "tree_id": "cdcb671f550effdb659b0dd8d363b68d2c30b685",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/43571100192f9d3aaa7d48ba29f0b5f7fddc3038"
        },
        "date": 1684965588959,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.49,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22781,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "068532fb8bd9e0cd13ef5741620da3722d1d6c5d",
          "message": "Update pyright, fix typing issues (#358)",
          "timestamp": "2023-05-26T12:37:02+02:00",
          "tree_id": "e77f15d9e03244b9a498dc8b43d3d93e3d128707",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/068532fb8bd9e0cd13ef5741620da3722d1d6c5d"
        },
        "date": 1685098155647,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.49,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22781,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "bbc6b12fce380614b7c26313e05d0cea0bc4c2f9",
          "message": "New combinational domains for cutting combinational paths (Multi-modules) (#337)",
          "timestamp": "2023-05-26T13:25:49+02:00",
          "tree_id": "8f5966539a25cd19d3b0041ee51b21cc0ada7756",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/bbc6b12fce380614b7c26313e05d0cea0bc4c2f9"
        },
        "date": 1685100820563,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.83,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21351,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "b04d5ebe4e0665d40a240812d59c2ff3497f4645",
          "message": "Fix a bug in JumpBranch Unit (#361)",
          "timestamp": "2023-05-26T14:01:15+02:00",
          "tree_id": "77d3bbb9ff4cebfeaf260ebf422f8b3ad923b60b",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/b04d5ebe4e0665d40a240812d59c2ff3497f4645"
        },
        "date": 1685103155510,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.31,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21988,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 438,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "75f0effa8dd324efcf65e7cd6eaf268885c51301",
          "message": "Add support for zmmul extension in the toolchain (#364)",
          "timestamp": "2023-05-26T14:10:33+02:00",
          "tree_id": "3afb889043bcf486ee067f5780f858b168c8c1d1",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/75f0effa8dd324efcf65e7cd6eaf268885c51301"
        },
        "date": 1685103414603,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.31,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21988,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 438,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "481d8e0dc327e37eb9eea6ce656a0e273d2ab4eb",
          "message": "Better names for transaction signals (#368)",
          "timestamp": "2023-05-26T18:05:13+02:00",
          "tree_id": "9d136a0a2ce9192dc7c276449a8740fa946d0455",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/481d8e0dc327e37eb9eea6ce656a0e273d2ab4eb"
        },
        "date": 1685117713297,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.62,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21214,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1b52e927d6276e5a212311e08c2b8a51e5020669",
          "message": "Nicer UnifierKey (#371)",
          "timestamp": "2023-05-31T00:22:25+02:00",
          "tree_id": "4730bcd54555fda2d48734aa5d9afc60b1c9fbf6",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/1b52e927d6276e5a212311e08c2b8a51e5020669"
        },
        "date": 1685485834985,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.62,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21214,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5dcc24c9972e58da8a77e3665a18a8ae202e55f7",
          "message": "Allow additional arguments in DependentCache (#356)",
          "timestamp": "2023-05-31T10:25:10+02:00",
          "tree_id": "3573b3a5b1b70b9ddbaaac36a3a97fd0c677e5a9",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/5dcc24c9972e58da8a77e3665a18a8ae202e55f7"
        },
        "date": 1685521971619,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.62,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21214,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e17c72e1124711add5e927c12f89413dbff07d33",
          "message": "Precommit (#370)",
          "timestamp": "2023-05-31T15:23:08+02:00",
          "tree_id": "5f67809be847f6eb0d4ec915642633c0dfce9225",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/e17c72e1124711add5e927c12f89413dbff07d33"
        },
        "date": 1685540018614,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 52.88,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22455,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7f27b718fd86e7a11cb80ab787037fb673ea166e",
          "message": "Core benchmarks (#363)",
          "timestamp": "2023-06-01T09:21:19+02:00",
          "tree_id": "49ecfaf43ae98497b1f4b153f10f7335e57bdb1b",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/7f27b718fd86e7a11cb80ab787037fb673ea166e"
        },
        "date": 1685604527559,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 52.88,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22455,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f22d67ada17b425d5e4d759d9549404cd1a2d2a4",
          "message": "Hopefully fix benchmark workflow (#373)",
          "timestamp": "2023-06-01T11:43:07+02:00",
          "tree_id": "381ba085799084d3cb5e79c9863a83179d704f99",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/f22d67ada17b425d5e4d759d9549404cd1a2d2a4"
        },
        "date": 1685613115086,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 52.88,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22455,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 860,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f2bcf12703b8b37e301522bdef2d9da8627fe0e9",
          "message": "Make fetcher ready for discarding multiple instructions (#375)",
          "timestamp": "2023-06-02T23:12:01+02:00",
          "tree_id": "107554c4d5dadde6d00b56d1c13e7015404e70b5",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/f2bcf12703b8b37e301522bdef2d9da8627fe0e9"
        },
        "date": 1685740905133,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.7,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 20896,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 864,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a903b181b1884403a2558d682777bf5dc6fb3651",
          "message": "Make verify_branch know its origin with from_pc (#378)",
          "timestamp": "2023-06-02T23:33:49+02:00",
          "tree_id": "41f8563314467cc9f70ec01ffd7ad94305b9b00d",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/a903b181b1884403a2558d682777bf5dc6fb3651"
        },
        "date": 1685742076888,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.59,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 25745,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 864,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cf1004ef9628fc3b7d2020e4c39d409311436706",
          "message": "Instruction decoder refactor (#379)",
          "timestamp": "2023-06-05T09:01:09+02:00",
          "tree_id": "841173c625873d45aeb07cf431c66d70821f1dca",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/cf1004ef9628fc3b7d2020e4c39d409311436706"
        },
        "date": 1685948981406,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 55.36,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 20807,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 438,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 864,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ebdabff1247eedb08004bd06dcd2c2eb7336d40a",
          "message": "Parametrize rs_entries in RSLayouts (#372)",
          "timestamp": "2023-06-05T09:17:07+02:00",
          "tree_id": "c1b76d3af644b6f5e9aedf358a9833853069bd95",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/ebdabff1247eedb08004bd06dcd2c2eb7336d40a"
        },
        "date": 1685949893815,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.56,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21882,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 864,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fd3857d23079b1e9c651e4b48381b361434228f8",
          "message": "ISA String improvements (#377)",
          "timestamp": "2023-06-05T11:31:11+02:00",
          "tree_id": "ec55139ad76e0945aca7c0d0ae9601c8a9b38261",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/fd3857d23079b1e9c651e4b48381b361434228f8"
        },
        "date": 1685957943242,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.56,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 20686,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 438,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 864,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "pazeraf@gmail.com",
            "name": "Filip Pazera",
            "username": "pa000"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "92439af1cd33c528137d1824e57dcbc25cfecc71",
          "message": "Zbc functional unit (#294)",
          "timestamp": "2023-06-07T15:15:23+02:00",
          "tree_id": "b86c7b3dbdf4c1c28988f3374e5ae76d29224d48",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/92439af1cd33c528137d1824e57dcbc25cfecc71"
        },
        "date": 1686144126284,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.91,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21538,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 864,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5608,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "324526@uwr.edu.pl",
            "name": "Wojciech Pokój",
            "username": "wojpok"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c43c51454414b7acf25a52ea3b97af65e085294e",
          "message": "ZBB extension (#369)",
          "timestamp": "2023-06-12T10:55:42+02:00",
          "tree_id": "f017659bbe01efafb5fc6ba8c4e0d916649f22bf",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/c43c51454414b7acf25a52ea3b97af65e085294e"
        },
        "date": 1686560720231,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.28,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21247,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 880,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5618,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8381ebb9476f3205371010edfe2eba358a975fa3",
          "message": "Remove dummy sync signal (#387)",
          "timestamp": "2023-06-14T09:48:06+02:00",
          "tree_id": "255762b7705e9ff5723f58e8f4ba528b516234ac",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/8381ebb9476f3205371010edfe2eba358a975fa3"
        },
        "date": 1686729341657,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 59.23,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21974,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 880,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5618,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "63d824f90f451100f2d2de523bb66282d6834f1f",
          "message": "Update Amaranth version (#392)",
          "timestamp": "2023-06-19T13:22:33+02:00",
          "tree_id": "d4282f77208e706f1839a85208fcb9ff10b85a91",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/63d824f90f451100f2d2de523bb66282d6834f1f"
        },
        "date": 1687174358220,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.83,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21825,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5623,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "712601e17afd3aef891651487a454908f3399869",
          "message": "Simultaneous transactions (#347)",
          "timestamp": "2023-06-22T20:56:17+02:00",
          "tree_id": "a7daa806d0abe77635e1e1ff859f0392657ca161",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/712601e17afd3aef891651487a454908f3399869"
        },
        "date": 1687460625220,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.07,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22114,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5623,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f5302ce9d42c5fbaecd1bf1dbe32d6ab7bd4681c",
          "message": "Try-product combiner (#391)",
          "timestamp": "2023-06-23T13:03:54+02:00",
          "tree_id": "463106b8295841f359e500761e10b8e2df981e12",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/f5302ce9d42c5fbaecd1bf1dbe32d6ab7bd4681c"
        },
        "date": 1687518974525,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.57,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 20698,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5623,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "95f038d1819ad9a919443dd7311cca6e42b34dd4",
          "message": "Layout for exceptions (#393)",
          "timestamp": "2023-06-23T15:19:34+02:00",
          "tree_id": "d6f0f7c2d315449290d80f7db682f939f5dc5518",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/95f038d1819ad9a919443dd7311cca6e42b34dd4"
        },
        "date": 1687526920158,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.73,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21546,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5623,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "324526@uwr.edu.pl",
            "name": "Wojciech Pokój",
            "username": "wojpok"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "75b1161f734c1be0ca8063d2b648defdb7cf1cfa",
          "message": "Encoding uniqueness (#388)",
          "timestamp": "2023-06-26T11:40:52+02:00",
          "tree_id": "1e6bf18541a503ca50c508443053e6fda5baaf4e",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/75b1161f734c1be0ca8063d2b648defdb7cf1cfa"
        },
        "date": 1687773315450,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 53.35,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22183,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 438,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5623,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "802d33498bdc94739ad6048dab2b696d15556012",
          "message": "Exception support (#386)",
          "timestamp": "2023-06-27T12:12:37+02:00",
          "tree_id": "8b6af11e6b5a4050a59bfbc9db2e32fa4ada6fec",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/802d33498bdc94739ad6048dab2b696d15556012"
        },
        "date": 1687861296402,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.64,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 20870,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5623,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cc5cc1740a758a11b8485627453afa85bb633ce8",
          "message": "MemoryBank and Serializer (#304)",
          "timestamp": "2023-06-27T15:09:19+02:00",
          "tree_id": "9e0498ff5b040e236aac06dfdee35afacf6e68fe",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/cc5cc1740a758a11b8485627453afa85bb633ce8"
        },
        "date": 1687871841839,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 54.91,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 23146,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5623,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f58fd958bde32881d6f8b40fc1c2e9039147022b",
          "message": "DummyLSU: Delay pushing store result until execution (#398)",
          "timestamp": "2023-06-28T12:21:39+02:00",
          "tree_id": "2d8b2665595b553e7b59752bd8b8bb050ce1532f",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/f58fd958bde32881d6f8b40fc1c2e9039147022b"
        },
        "date": 1687948171317,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 61.3,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21078,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 438,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5621,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "24831d688ef84c9a22b1e1d28f9f2f6995faa0e7",
          "message": "Synthesize different core versions (#407)",
          "timestamp": "2023-06-30T19:16:15+02:00",
          "tree_id": "d1155c0f1fa5af0e559571c62e4e008b2e852372",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/24831d688ef84c9a22b1e1d28f9f2f6995faa0e7"
        },
        "date": 1688145944220,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21242,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5621,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "02ade9b3b62130fd43613c133f0795f9b8b4e590",
          "message": "auto_debug_signals: drop useless empty objects (#418)",
          "timestamp": "2023-07-03T09:54:37+02:00",
          "tree_id": "0b617871cc95985f0d03f07726694063ce08bdff",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/02ade9b3b62130fd43613c133f0795f9b8b4e590"
        },
        "date": 1688371332794,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.95,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 23488,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5621,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e766ced0918cea36aaddf5b491535fc0859e67ef",
          "message": "\"C\" Standard Extension for Compressed Instructions (#343)",
          "timestamp": "2023-07-03T10:05:38+02:00",
          "tree_id": "5d44c916f4ce4bcc7b4a0ae498b047f400e033a3",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/e766ced0918cea36aaddf5b491535fc0859e67ef"
        },
        "date": 1688372095764,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.96,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21995,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5621,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "324526@uwr.edu.pl",
            "name": "Wojciech Pokój",
            "username": "wojpok"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "de5279129166eed9b2311f9e9fa4fc3935466ac8",
          "message": "Division unit (#389)",
          "timestamp": "2023-07-03T11:38:04+02:00",
          "tree_id": "4080e1f3982cece53f160cbfa11a749aa94822bf",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/de5279129166eed9b2311f9e9fa4fc3935466ac8"
        },
        "date": 1688377713720,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.9,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 20281,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5621,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "98f5b887708e7b3cfa0456bc3b7f828b0488a602",
          "message": "Use Zbc and Zbs in full core (#421)",
          "timestamp": "2023-07-03T14:01:00+02:00",
          "tree_id": "bb2ab9d118ffffc4d31965d88232339329bf6fd3",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/98f5b887708e7b3cfa0456bc3b7f828b0488a602"
        },
        "date": 1688386027669,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 52.92,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22129,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5621,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "18ec74480a04c0f89879ce6fe518c0b18dac7fd9",
          "message": "Fix isa string generation (#424)",
          "timestamp": "2023-07-03T15:04:01+02:00",
          "tree_id": "6390a018b0e22dfec7501a130e1b4a9ddd70313a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/18ec74480a04c0f89879ce6fe518c0b18dac7fd9"
        },
        "date": 1688389959218,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.55,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 20932,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5621,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1799f5e77fccd9077c4039bf4ba6a705e6cd9180",
          "message": "Make timeouts bigger (#426)",
          "timestamp": "2023-07-03T15:58:39+02:00",
          "tree_id": "be9b28f0453009cd382d4739f66d820023f17cce",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/1799f5e77fccd9077c4039bf4ba6a705e6cd9180"
        },
        "date": 1688393107407,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.58,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21601,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 888,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5621,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3e3b1715429501e341dd0dc12f6c66dbb63d8493",
          "message": "Exceptions implementation (#394)",
          "timestamp": "2023-07-03T16:09:24+02:00",
          "tree_id": "a46717caf38ffc8da1cb2d34b098039e39fd574d",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/3e3b1715429501e341dd0dc12f6c66dbb63d8493"
        },
        "date": 1688393794228,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 57.68,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16824,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 868,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5618,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6bf3b70c715c000e46e9eeedf1548bf566e0d831",
          "message": "Remove wiki deploy (#423)",
          "timestamp": "2023-07-03T16:20:17+02:00",
          "tree_id": "b28e80060e450568692689ddf53fba345b30ed20",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/6bf3b70c715c000e46e9eeedf1548bf566e0d831"
        },
        "date": 1688394442229,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.94,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16735,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 868,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5618,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "df6653bed7ab1e4a3331a76e9397ed4dc5b28f94",
          "message": "Simplified DummyLSU (#427)",
          "timestamp": "2023-07-05T10:04:45+02:00",
          "tree_id": "c868af0fb16744d8440a6fce02683d7588f791b4",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/df6653bed7ab1e4a3331a76e9397ed4dc5b28f94"
        },
        "date": 1688544656989,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.38,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16498,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 868,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5615,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "263095dcd4f32c100231bad2f61ad269ee653712",
          "message": "Single caller method check (#425)",
          "timestamp": "2023-07-05T11:13:41+02:00",
          "tree_id": "8ab0e869c67c6969b51db2e35075bd24b0181d5a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/263095dcd4f32c100231bad2f61ad269ee653712"
        },
        "date": 1688548713892,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 59.71,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16630,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 868,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5615,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "654117c1c76a892627dc4734f6cc2936e0f03975",
          "message": "Change default value for nonblocking (#415)",
          "timestamp": "2023-07-08T11:13:35+02:00",
          "tree_id": "703e7f5dd32f81f783b04c54685789404979f600",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/654117c1c76a892627dc4734f6cc2936e0f03975"
        },
        "date": 1688808335627,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 58.34,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17439,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 868,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5615,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "Kristopher38@wp.pl",
            "name": "Krzysztof Obłonczek",
            "username": "Kristopher38"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6344da745a97aa22bec2c6dad67357c97e001494",
          "message": "Use all available cores when compiling cocotb regression tests with verilator (#430)",
          "timestamp": "2023-07-10T12:07:24+02:00",
          "tree_id": "493a60b72edba7b70036367f533ccb07467a123d",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/6344da745a97aa22bec2c6dad67357c97e001494"
        },
        "date": 1688984103205,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 62.77,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17069,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 868,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5615,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fcba37657d00309fee22f63d45d1341918d2012d",
          "message": "Improve GenericFunctionalTestUnit (#433)",
          "timestamp": "2023-07-11T21:34:19+02:00",
          "tree_id": "49a81cd4b9dd011c1b4bbca5396dc832e1a49845",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/fcba37657d00309fee22f63d45d1341918d2012d"
        },
        "date": 1689104450690,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.13,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17161,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 868,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5615,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "de07d43dd31e5b05c361c0cb6825431e92992d8f",
          "message": "Method run debugging (#432)",
          "timestamp": "2023-07-11T21:53:54+02:00",
          "tree_id": "5e737f38d73ab2d7ee421e1315b8fd563a8278c4",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/de07d43dd31e5b05c361c0cb6825431e92992d8f"
        },
        "date": 1689105592101,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 61.21,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 16561,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 868,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5615,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5bf55b86d82d6fb4f4e163c33754466c993e4224",
          "message": "DummyLSU: add FENCE (#441)",
          "timestamp": "2023-07-12T10:10:13+02:00",
          "tree_id": "8bc43b04a38aa1a8e2bf0e1e4364af706bc91af9",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/5bf55b86d82d6fb4f4e163c33754466c993e4224"
        },
        "date": 1689149975788,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 53.47,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 17475,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 470,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 884,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 5619,
            "unit": "LUT"
          }
        ]
      }
    ],
    "Fmax and LCs (full)": [
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "24831d688ef84c9a22b1e1d28f9f2f6995faa0e7",
          "message": "Synthesize different core versions (#407)",
          "timestamp": "2023-06-30T19:16:15+02:00",
          "tree_id": "d1155c0f1fa5af0e559571c62e4e008b2e852372",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/24831d688ef84c9a22b1e1d28f9f2f6995faa0e7"
        },
        "date": 1688146013954,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 53.1,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 20407,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1048,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 980,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 6620,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "arek_koz@o2.pl",
            "name": "Arusekk",
            "username": "Arusekk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "02ade9b3b62130fd43613c133f0795f9b8b4e590",
          "message": "auto_debug_signals: drop useless empty objects (#418)",
          "timestamp": "2023-07-03T09:54:37+02:00",
          "tree_id": "0b617871cc95985f0d03f07726694063ce08bdff",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/02ade9b3b62130fd43613c133f0795f9b8b4e590"
        },
        "date": 1688371500372,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 56.18,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 20135,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1048,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 980,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 6620,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "xthaid@gmail.com",
            "name": "Jakub Urbańczyk",
            "username": "xThaid"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e766ced0918cea36aaddf5b491535fc0859e67ef",
          "message": "\"C\" Standard Extension for Compressed Instructions (#343)",
          "timestamp": "2023-07-03T10:05:38+02:00",
          "tree_id": "5d44c916f4ce4bcc7b4a0ae498b047f400e033a3",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/e766ced0918cea36aaddf5b491535fc0859e67ef"
        },
        "date": 1688372126655,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 51.06,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 24006,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1080,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 948,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 6665,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "324526@uwr.edu.pl",
            "name": "Wojciech Pokój",
            "username": "wojpok"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "de5279129166eed9b2311f9e9fa4fc3935466ac8",
          "message": "Division unit (#389)",
          "timestamp": "2023-07-03T11:38:04+02:00",
          "tree_id": "4080e1f3982cece53f160cbfa11a749aa94822bf",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/de5279129166eed9b2311f9e9fa4fc3935466ac8"
        },
        "date": 1688377874293,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 53.34,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21607,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1466,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 1012,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 6808,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "18ec74480a04c0f89879ce6fe518c0b18dac7fd9",
          "message": "Fix isa string generation (#424)",
          "timestamp": "2023-07-03T15:04:01+02:00",
          "tree_id": "6390a018b0e22dfec7501a130e1b4a9ddd70313a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/18ec74480a04c0f89879ce6fe518c0b18dac7fd9"
        },
        "date": 1688390522534,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 47.54,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22262,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1472,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 1060,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 8172,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3e3b1715429501e341dd0dc12f6c66dbb63d8493",
          "message": "Exceptions implementation (#394)",
          "timestamp": "2023-07-03T16:09:24+02:00",
          "tree_id": "a46717caf38ffc8da1cb2d34b098039e39fd574d",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/3e3b1715429501e341dd0dc12f6c66dbb63d8493"
        },
        "date": 1688394008193,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 46.69,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 26120,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1472,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 1052,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 8172,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1799f5e77fccd9077c4039bf4ba6a705e6cd9180",
          "message": "Make timeouts bigger (#426)",
          "timestamp": "2023-07-03T15:58:39+02:00",
          "tree_id": "be9b28f0453009cd382d4739f66d820023f17cce",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/1799f5e77fccd9077c4039bf4ba6a705e6cd9180"
        },
        "date": 1688394298641,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 49.02,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22700,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1472,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 1060,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 8172,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6bf3b70c715c000e46e9eeedf1548bf566e0d831",
          "message": "Remove wiki deploy (#423)",
          "timestamp": "2023-07-03T16:20:17+02:00",
          "tree_id": "b28e80060e450568692689ddf53fba345b30ed20",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/6bf3b70c715c000e46e9eeedf1548bf566e0d831"
        },
        "date": 1688394855544,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 47.64,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22185,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1472,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 1052,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 8172,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "df6653bed7ab1e4a3331a76e9397ed4dc5b28f94",
          "message": "Simplified DummyLSU (#427)",
          "timestamp": "2023-07-05T10:04:45+02:00",
          "tree_id": "c868af0fb16744d8440a6fce02683d7588f791b4",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/df6653bed7ab1e4a3331a76e9397ed4dc5b28f94"
        },
        "date": 1688545009719,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 48.93,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22323,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1472,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 1052,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 8169,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "263095dcd4f32c100231bad2f61ad269ee653712",
          "message": "Single caller method check (#425)",
          "timestamp": "2023-07-05T11:13:41+02:00",
          "tree_id": "8ab0e869c67c6969b51db2e35075bd24b0181d5a",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/263095dcd4f32c100231bad2f61ad269ee653712"
        },
        "date": 1688549214450,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 49.01,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21966,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1472,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 1052,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 8169,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "34948061+lekcyjna123@users.noreply.github.com",
            "name": "lekcyjna123",
            "username": "lekcyjna123"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "654117c1c76a892627dc4734f6cc2936e0f03975",
          "message": "Change default value for nonblocking (#415)",
          "timestamp": "2023-07-08T11:13:35+02:00",
          "tree_id": "703e7f5dd32f81f783b04c54685789404979f600",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/654117c1c76a892627dc4734f6cc2936e0f03975"
        },
        "date": 1688808868506,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 49.87,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 21517,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1472,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 1052,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 8169,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "Kristopher38@wp.pl",
            "name": "Krzysztof Obłonczek",
            "username": "Kristopher38"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6344da745a97aa22bec2c6dad67357c97e001494",
          "message": "Use all available cores when compiling cocotb regression tests with verilator (#430)",
          "timestamp": "2023-07-10T12:07:24+02:00",
          "tree_id": "493a60b72edba7b70036367f533ccb07467a123d",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/6344da745a97aa22bec2c6dad67357c97e001494"
        },
        "date": 1688984422842,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 47.43,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 23462,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1440,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 1052,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 8169,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fcba37657d00309fee22f63d45d1341918d2012d",
          "message": "Improve GenericFunctionalTestUnit (#433)",
          "timestamp": "2023-07-11T21:34:19+02:00",
          "tree_id": "49a81cd4b9dd011c1b4bbca5396dc832e1a49845",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/fcba37657d00309fee22f63d45d1341918d2012d"
        },
        "date": 1689104722409,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 49.42,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 24296,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1472,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 1052,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 8169,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "tilk@tilk.eu",
            "name": "Marek Materzok",
            "username": "tilk"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "de07d43dd31e5b05c361c0cb6825431e92992d8f",
          "message": "Method run debugging (#432)",
          "timestamp": "2023-07-11T21:53:54+02:00",
          "tree_id": "5e737f38d73ab2d7ee421e1315b8fd563a8278c4",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/de07d43dd31e5b05c361c0cb6825431e92992d8f"
        },
        "date": 1689105724687,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 46.82,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 22842,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1440,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 1052,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 8169,
            "unit": "LUT"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "piotro888@wp.pl",
            "name": "piotro888",
            "username": "piotro888"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5bf55b86d82d6fb4f4e163c33754466c993e4224",
          "message": "DummyLSU: add FENCE (#441)",
          "timestamp": "2023-07-12T10:10:13+02:00",
          "tree_id": "8bc43b04a38aa1a8e2bf0e1e4364af706bc91af9",
          "url": "https://github.com/kuznia-rdzeni/coreblocks/commit/5bf55b86d82d6fb4f4e163c33754466c993e4224"
        },
        "date": 1689150531495,
        "tool": "customBiggerIsBetter",
        "benches": [
          {
            "name": "Max clock frequency (Fmax)",
            "value": 43.32,
            "unit": "MHz"
          },
          {
            "name": "Device utilisation: (ECP5)",
            "value": 26652,
            "unit": "LUT4"
          },
          {
            "name": "LUTs used as carry: (ECP5)",
            "value": 1440,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as ram: (ECP5)",
            "value": 1052,
            "unit": "LUT"
          },
          {
            "name": "LUTs used as DFF: (ECP5)",
            "value": 8169,
            "unit": "LUT"
          }
        ]
      }
    ]
  }
}