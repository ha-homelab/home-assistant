# Email in Home Assistant

Incoming mail is already configured through two integrations: the built-in
**IMAP** integration reads Gmail mailbox state, and **Mail and Packages** reads
delivery messages and exposes USPS, Amazon, UPS and other shipment sensors.
Both integrations are configured in Home Assistant storage; mailbox credentials
and message contents are not repository configuration.

The former HACS Email Sensor had no configured mailbox. Its successor,
**Tracking Numbers**, was also unconfigured and has been uninstalled. Neither is
required for the existing incoming-mail integrations or outgoing SMTP.

## USPS dashboard and scan recovery (2026-09-30)

Mail and Packages 0.6.3 reads the dedicated Gmail label `USPS Maria`, every five
minutes. This contains the household digest forwarded from Maria, not the direct
digest addressed to the receiving account. At the initial dashboard repair, HA
was still reading the old `USPS778` label. Authentication and parsing worked: today's digest arrived at 07:19 Pacific, the mail
sensor changed at 07:22, and the integration generated its envelope preview.
The Overview Home view only referenced the count sensor in its feed and an
entities list; it had no card connected to the current USPS camera. The feed
entry itself was visible during the investigation. This was not a lost Gmail
connection or a missing current entity.

A native **USPS Mail — Maria** card is now at the start of Overview/Home. Its
reproducible configuration is [dashboards/usps-mail.yaml](dashboards/usps-mail.yaml).
It shows mail previews, packages, the last successful scan, and today's envelope
image. The original feed and all other dashboard content remain unchanged.
`camera.imap_gmail_com_mail_usps_camera` follows the integration's randomized
image filename; do not hardcode a `/local/.../<uuid>.gif` URL that changes daily.
The camera serves locally generated mail images, not an IP-camera video stream.

The existing 30-second limit applies to the **entire scan**, including every
selected carrier search. Two scans exceeded it during the investigation day.
The integration options now allow 90 seconds, retain the five-minute interval
and all existing carriers, and also select **Mail Updated**. This exposes
`sensor.imap_gmail_com_mail_updated` so a stalled scanner can be distinguished
from an unchanged daily count. No extra scheduled scans were added. Credentials
remain in the existing configuration entry; only that integration was reloaded.

### Selecting the forwarded household report

The receiving Gmail account contains two USPS digests with the same daily
subject. Gmail groups them into one conversation and can display the `USPS778`
label beside Maria's message, even though IMAP confirms that label belongs only
to the direct message. Maria's forwarded copies retained their original `To`
address and the original USPS `From`, plus Gmail's `X-Forwarded-For` and
`X-Forwarded-To` headers. They were in the inbox without the label HA searched.

A separate **USPS Maria** label and Gmail filter now isolate the intended source.
The filter's search criterion is:

```text
to:<Maria's Gmail address> {from:usps.com from:usps.gov}
```

Replace the bracketed recipient with the verified original `To` address from
Maria's forwarded digest. Its only action is **Apply label: USPS Maria**. It
does not archive, forward, delete, mark read, or change spam handling. The seven
most recent matching forwarded messages were backfilled individually through
IMAP after checking their recipient and forwarding headers; their read flags
were verified unchanged. Do not bulk-apply to matching Gmail conversations,
which may also contain the direct report. The old label/filter are retained.

HA now selects only `USPS Maria`. Entity IDs, login credentials, carrier
selections, the 90-second budget and five-minute interval remain unchanged.
Gmail automatic forwarding preserves the USPS sender, so an additional
`forwarded_emails` sender override is unnecessary. Gmail filter rules are outside
the HA backup and must be recreated separately if that Gmail configuration is
lost. The household source is verified at the individual-message level, not by
conversation labels in the Gmail UI.

The upstream USPS count is based on accepted preview images, including supported
placeholders, rather than the digest's headline total. A no-mail placeholder can
therefore count as one preview while the actual report says zero mailpieces.
The packages sensor tracks separate shipment notices; it does not read the
headline package count from the daily digest. The card calls these values
**Mail previews** and **Tracked packages** to distinguish their meaning. On the
verification day Maria's digest reported zero mailpieces and two inbound
packages; the camera correctly switched from the direct report's envelope to
the no-mail placeholder. No upstream parser code was changed.

To restore after recovery:

1. Restore the storage-managed Mail and Packages entry and its Gmail credentials
   from the HA backup. Preserve its current entity IDs.
2. Recreate the Gmail label/filter above if necessary, then select only
   `USPS Maria` in the integration options. Keep the existing carrier selections,
   select **Mail Updated**, set the scan time limit to **90 seconds**, and keep
   the scan interval at **5 minutes**.
3. Add the versioned card to the Home view using the dashboard editor or the
   Lovelace API. Check for an existing copy first. Keep snapshots private and
   compare the current dashboard before saving to avoid overwriting other edits.
4. Verify the entry is loaded, the last-success timestamp advances on a regular
   scan, and the authenticated camera proxy returns a decodable image that
   matches today's forwarded household digest (including its no-mail placeholder). Inspect Gmail with read-only IMAP and
   `BODY.PEEK` when diagnosing; do not change message flags or delete mail.

To roll back the source selection, select the prior `USPS778` folder through
the options flow; that restores the direct report. The new label/filter can be
removed separately without deleting any messages. For dashboard/timeout rollback,
remove only the added card and return the scan limit to its prior value through
the options flow. The additional Mail Updated sensor can remain
or be deselected there. Do not replace the whole dashboard with an old backup
if later edits exist. No HA restart or automation reload is needed.

Reference: [Mail and Packages documentation](https://github.com/moralmunky/Home-Assistant-Mail-And-Packages/wiki).

## Outgoing notifications

The SMTP integration now uses the existing **Brevo** account also used by
`venus-os-observability/alert-mqtt-bridge`. Its current deployment runs as
`venus-alert-bridge` on Synology. The bridge already sends Grafana alerts through
Brevo; Home Assistant connects directly to the same provider.

- Server: `smtp-relay.brevo.com`, port `587`.
- Security: STARTTLS, certificate verification enabled, 20-second timeout.
- Credentials: existing Brevo SMTP login/key, stored only in the HA config entry.
- Sender and recipient: the existing configured and verified monitoring addresses.
- Sender name: `My Home Assistant`.
- Notification entity: `notify.mailit`.

Send an explicitly selected notification through the entity action:

```yaml
action: notify.send_message
target:
  entity_id: notify.mailit
data:
  title: Home Assistant
  message: Example notification
```

For HTML and attachments, use `smtp.send_message` with the same target. The old
`notify.mailit` action is distinct from the new entity ID. No automation or script
in the managed libraries referenced that old action, and this change does not
add email delivery to existing motion or device-event notifications.

The obsolete YAML SMTP platform pointed to a local server on port 25 and failed
to import into the current SMTP integration. It has been removed from
`config/notify.yaml`; do not reintroduce SMTP credentials or the deprecated YAML
platform there. Create or reconfigure SMTP under **Settings → Devices & services**.
Use the provider's SMTP key, not a Gmail mailbox password or a Brevo API key.

## Verification and recovery

The HA configuration flow checks connection, TLS and authentication without
sending mail. After adding the recipient, verify the integration is loaded and
`notify.mailit` exists. This does not prove end-to-end mailbox delivery; a real
test email requires a separately requested send. Do not infer success from the
mere presence of the configuration entry.

The Overview dashboard had three references to the retired
`sensor.mail_usps_mail` / `sensor.mail_usps_packages` identities. They were changed
to the active `sensor.imap_gmail_com_mail_usps_mail` and
`sensor.imap_gmail_com_mail_usps_packages` entities using the Lovelace API. The
dashboard is storage-managed and its private pre-change copy is retained outside
Git. All 20 obsolete Mail and Packages registry entities have now been removed
after checking the active dashboards, configuration files and blueprints for
references. The current Mail and Packages entities and the IMAP and SMTP entries
are preserved. Their private pre-change snapshots are retained outside Git.

To recover the outgoing configuration, restore the Home Assistant backup or
recreate the SMTP config entry and recipient with the settings above, then keep
the notification entity ID `notify.mailit`. A Git checkout alone cannot recover
storage-managed integration credentials. To disable this channel, disable its
SMTP config entry; incoming Gmail and shipment sensors are independent.

References: [Home Assistant SMTP](https://www.home-assistant.io/integrations/smtp/),
[Brevo SMTP](https://help.brevo.com/hc/en-us/articles/7924908994450-Send-transactional-emails-using-Brevo-SMTP).
