# Map the stock whole-machine serial through legacy stats

Accepted for PROD-2162. Map the optional unique legacy `Miner Serial` field to
existing `MinerData.serial_number`, reusing `legacy_stats` with MAC and PSU
readers. Public getter and include/exclude selection retain the normal data
location machinery and request error attribution. Board and PSU serials are
independent; missing old-firmware fields return `None`.

CGMiner reads only `/config/sn` with a raw 256-byte limit and trims ASCII
whitespace. Valid values contain 1–128 printable non-whitespace ASCII bytes,
retain case, and exclude `unknown`, `n/a`, `na`, `none`, `null` (case-insensitive)
and all-zero strings. The parser rejects non-strings and ambiguous rows.
Deployment must verify that `/config` comes from stock `mtd5/config`, not
Nonce `mtd6/nvdata`. Neither this adapter nor Agent mounts or repairs it.

Review revision 2026-09-27: all three SN readers use
normalize_antminer_like_serial_number, the existing Antminer policy. Pyasic
does not duplicate the CGMiner-only ASCII, length or all-zero restrictions.
The machine reader still rejects non-string values and ambiguous rows; board
EEPROM and PSU identity validity gates remain. The normalizer strips whitespace,
rejects shared placeholders and error values, and filters its existing all-zero
pattern. Other backends and CGMiner export validation remain unchanged.
