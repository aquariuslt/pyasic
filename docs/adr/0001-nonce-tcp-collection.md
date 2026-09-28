# Dedicated Nonce CGMiner adapter

Accepted for PROD-2126, updated 2026-09-26. Identify Nonce firmware by VERSION.Firmware=Nonce within Antminer discovery, then select the S21+ backend by VERSION.Model. The Nonce API version field is not an identification gate; absent or different version values do not prevent discovery. Use TCP read commands only. Each collection reuses one nested stats response, one nested summary response and one legacy stats MAC/PSU response. The private legacy_stats key sends command=stats without new_api; it never collides with the nested stats key. Transport/API errors remain isolated by request.

Keep legacy_stats as the logical command through the shared request/error counters, translating it to stats only at the byte transport boundary. This separates concurrent new and legacy stats failures without changing the wire protocol or the shared RPC interfaces. Both request completion orders must preserve field transport errors and the all_requests_failed verdict; a subsequent successful read clears them.

Require STATUS/INFO/STATS and STATUS/INFO/SUMMARY reference envelopes. Preserve original MinerData, HashBoard, Fan, PowerSupply, generic aggregation; DataOptions now formally includes VOLTAGE. Use the base get_data_with_errors interface: parser errors remain in MinerDataReadResult.field_parse_errors and request failures in field_transport_errors, outside miner JSON. No public mining_state or firmware-specific model is introduced.

SUMMARY.rate_5s in GH/s supplies raw_hashrate and is_mining; cumulative rate_avg is not a fallback. A successful summary with missing/invalid five-second evidence yields unavailable hashrate and False mining state. Transport failures, decode failures and non-success STATUS responses retain the model default and field_transport_errors; default True is not evidence of mining. Other fields can still succeed. The old summary wire API remains compatible for its existing callers.

An unrequested or excluded is_mining field keeps the standard model default; that default is not evidence of mining. Error-code reads use the base empty implementation without sending stats. Whole-machine serial reads use legacy stats as specified in ADR 0002. The base model supplies the expected total of 165 chips. Missing pool share counters remain nullable and do not discard a pool with valid alive/active flags; shared percentage calculations return 0 when their denominator is unavailable.

The S21+ model supplies three boards, 55 chips per board and four fans. The Nonce backend uses these model properties; an unknown model uses reported slots and fan count without S21+ expectations. Observed chip count or valid EEPROM serial establishes presence. Map valid sn to serial_number and finite nonnegative freq_avg to MHz chip_frequency. Map temp_pcb[0]/[2] to inlet_temp/outlet_temp and average only actual PCB sensor positions [1]/[3] into temp. Preserve all four raw positions; there is no air-plus-15 or chip/PIC estimate. Preserve fan order and legal zero.

Select one unambiguous legacy PSU row. Identity-valid nonempty serial becomes psus[0].serial_number. Per-channel valid, finite nonnegative power/voltage with finite age 0..30000 ms become wattage/voltage. Round watts decimal half-up into the existing int field. Measurement side unconfirmed is accepted for wattage by explicit user decision, but remains a raw diagnostic. Do not sum PSU values across boards, infer current from raw registers, or merge three temperatures into PowerSupply.temperature. A failed temperature channel or historical read error does not invalidate currently valid power/voltage. Parse numeric JSON without the generic nan/inf-to-zero repair.

Unavailable PSU data clears optional fields in the current snapshot; no old-cache fallback exists. MAC independently selects the unique legacy row marked MAC Error. Accept only integer zero plus a six-octet, nonzero unicast MAC, normalized to lowercase. Missing, malformed, ambiguous or failed reads return None; no cached identity is reused. Whole-machine serial is independent of MAC, board and PSU serials. Agent applies its existing collection and reporting policy. Synthetic C-export/TCP/cache tests and builds do not replace complete-device acceptance.

Review revision 2026-09-27: use NonceFirmware -> Nonce -> NonceS21Plus and
NonceUnknown(Nonce, AntMinerMake), without StockFirmware inheritance. Public
getters use the standard internal getter fallback: supplied replies are reused,
None triggers a direct RPC read. Failed stats, summary and legacy_stats batch
reads supply an explicit empty response to their parsers, so fields retain the
batch failure without issuing per-field retries. Direct getters still send one
request when no response is supplied. No new retry or cache mechanism is added.
Voltage is a standard data option and Agent hot field, without dynamic
DataLocations or include injection.

For these three batch reads, a non-success STATUS is a field-level request
failure even though the device returned an envelope. Record it before supplying
the empty parser response. This preserves stored cold identity in Agent and
keeps mining state unknown rather than treating the error as stopped mining.

The CGMiner exporter fixes temp_pcb to [actual inlet, null, actual outlet, null]
and exports no chip temperatures. Thus temp/temperature_avg remain unknown;
these are not filled with an inlet/outlet average. See driver-s21plus-cgminer.c
(sensor loop in s21plus new stats export) and docs/s21plus-telemetry-api.md.
PoolMetrics missing-counter denominator guards are shared across all firmware.
