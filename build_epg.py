import gzip
import re
import urllib.request
import xml.etree.ElementTree as ET

M3U_URL = "https://raw.githubusercontent.com/PK70242/test/refs/heads/main/Sick"

# Regional XMLTV sources covering IN, UK, US, AU, PK
EPG_SOURCES = [
    "https://epgshare01.online/epgshare01/epg_ripper_IN1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_IN4.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_AU1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_PK1.xml.gz",
]

# Maps your playlist's tvg-id (or lowercase channel name) -> possible XMLTV IDs/names in public feeds
CHANNEL_ALIASES = {
    "willowsports": ["willow.us", "willowhd.us", "willow cricket", "willow sports"],
    "b0hm4zht1f": ["willow.us", "willowhd.us", "willow cricket"],
    "skycricket": ["skysportscricket.uk", "sky sports cricket", "sky cricket"],
    "skysportscricket.uk": ["skysportscricket.uk", "sky sports cricket"],
    "foxcricket.in": ["foxcricket.au", "foxsports501.au", "fox cricket", "fox sports 501"],
    "geo super": ["geosuper.pk", "geo super"],
    "a3d48c46-7902-45e2-abf9-0fab60c4d117": ["asports.pk", "a sports", "a sports hd"],
    "star sports 1 hd": ["starsports1hd.in", "star sports 1 hd", "star sports 1"],
    "star sports 1 hindi hd": ["starsports1hindihd.in", "star sports 1 hindi hd", "star sports 1 hindi"],
    "star_sports_hindi_1": ["starsports1hindihd.in", "star sports 1 hindi hd", "star sports 1 hindi"],
    "star sports 2 hd": ["starsports2hd.in", "star sports 2 hd", "star sports 2"],
    "star sports 2 hindi hd": ["starsports2hindihd.in", "star sports 2 hindi hd", "star sports 2 hindi"],
    "star sports select 1 hd": ["starsportsselect1hd.in", "star sports select 1 hd", "star sports select 1"],
    "star sports select 2 hd": ["starsportsselect2hd.in", "star sports select 2 hd", "star sports select 2"],
    "sony sports ten 1 hd.in": ["sonysportsten1hd.in", "sony sports ten 1 hd", "sony ten 1 hd"],
    "sony sports ten 2 hd.in": ["sonysportsten2hd.in", "sony sports ten 2 hd", "sony ten 2 hd"],
    "sony sports ten 3 hd.in": ["sonysportsten3hd.in", "sony sports ten 3 hd", "sony ten 3 hd"],
    "sony sports ten 5 hd.in": ["sonysportsten5hd.in", "sony sports ten 5 hd", "sony ten 5 hd"],
    "tntsports1": ["tntsports1.uk", "tnt sports 1", "tnt sports 1 hd"],
    "019de785-3a0f-7a8d-aa40-1bc1d60c9817": ["tntsports1.uk", "tnt sports 1"],
    "tntsports2": ["tntsports2.uk", "tnt sports 2", "tnt sports 2 hd"],
    "tntsports3": ["tntsports3.uk", "tnt sports 3", "tnt sports 3 hd"],
    "tntsports4": ["tntsports4.uk", "tnt sports 4", "tnt sports 4 hd"],
    "223": ["ddsports.in", "dd sports", "dd sports hd"],
    "foxsports1.us": ["foxsports1.us", "fs1.us", "fox sports 1"],
    "foxsports2.us": ["foxsports2.us", "fs2.us", "fox sports 2"],
    "f1channel.us": ["f1tv.us", "skyf1.uk", "sky sports f1"],
}


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        return gzip.decompress(raw) if url.endswith(".gz") else raw


def parse_m3u(m3u_text):
    # Returns dict: {output_channel_id: display_name}
    targets = {}
    for line in m3u_text.splitlines():
        line = line.strip()
        if not line.startswith("#EXTINF"):
            continue
        id_m = re.search(r'tvg-id="([^"]*)"', line)
        name_m = re.search(r',([^,]+)$', line)
        tvg_id = id_m.group(1).strip() if id_m else ""
        disp_name = name_m.group(1).strip() if name_m else ""

        # Skip sub-playlist entries (.m3u)
        if disp_name.lower().endswith(".m3u"):
            continue

        # Use tvg-id if present, otherwise display name (matches how IPTV players fall back)
        out_id = tvg_id if tvg_id else disp_name
        if out_id and out_id not in targets:
            targets[out_id] = disp_name
    return targets


def normalize(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


def build_epg():
    m3u_text = fetch_bytes(M3U_URL).decode("utf-8", errors="ignore")
    targets = parse_m3u(m3u_text)

    # Build lookup map: normalized alias -> list of target output IDs
    alias_to_targets = {}
    for out_id, disp_name in targets.items():
        keys = {out_id.lower(), disp_name.lower()}
        keys.update(CHANNEL_ALIASES.get(out_id.lower(), []))
        keys.update(CHANNEL_ALIASES.get(disp_name.lower(), []))
        for k in keys:
            norm = normalize(k)
            if norm:
                alias_to_targets.setdefault(norm, []).append(out_id)

    out_root = ET.Element("tv", {"generator-info-name": "Tailored-Sports-EPG"})
    written_channels = set()
    # Map (source_url, source_channel_id) -> list of target out_ids
    source_id_map = {}

    for src in EPG_SOURCES:
        try:
            root = ET.fromstring(fetch_bytes(src))
        except Exception as e:
            print(f"[WARN] Failed {src}: {e}")
            continue

        for ch in root.findall("channel"):
            src_cid = ch.get("id", "")
            names = [src_cid] + [dn.text or "" for dn in ch.findall("display-name")]
            matched_out_ids = []
            for n in names:
                matched_out_ids.extend(alias_to_targets.get(normalize(n), []))

            for out_id in set(matched_out_ids):
                source_id_map.setdefault((src, src_cid), []).append(out_id)
                if out_id not in written_channels:
                    new_ch = ET.Element("channel", {"id": out_id})
                    dn = ET.SubElement(new_ch, "display-name")
                    dn.text = targets[out_id]
                    out_root.append(new_ch)
                    written_channels.add(out_id)

        for prog in root.findall("programme"):
            src_cid = prog.get("channel", "")
            for out_id in set(source_id_map.get((src, src_cid), [])):
                # Only pull programmes from the first source that matched this channel
                new_prog = ET.fromstring(ET.tostring(prog))
                new_prog.set("channel", out_id)
                out_root.append(new_prog)

    xml_bytes = ET.tostring(out_root, encoding="utf-8", xml_declaration=True)
    with gzip.open("epg.xml.gz", "wb") as f:
        f.write(xml_bytes)

    missing = [v for k, v in targets.items() if k not in written_channels]
    print(f"Matched {len(written_channels)}/{len(targets)} channels.")
    if missing:
        print("Unmatched channels (mostly dynamic event streams):", ", ".join(missing))


if __name__ == "__main__":
    build_epg()
