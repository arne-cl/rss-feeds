#!/usr/bin/env python3
"""Build a podcast feed for VRT Radio 1's "Duyster" show (VRT MAX).

The show (https://www.vrt.be/vrtmax/luister/radio/d/duyster~11-177/)
is not published as a podcast by VRT, and the VRT MAX page is fully
client-rendered: all data comes from the public GraphQL API at
https://www.vrt.be/vrtnu-api/graphql/public/v1 (no auth).

- The ProgramPage query (pageId = the URL path) returns the episode
  tile list (~10 most recent broadcasts; VRT purges older ones — the
  merge logic keeps everything already collected).
- Tile dates are display strings without a year, so each new episode
  is enriched via the EpisodePage query, which carries the exact
  broadcastStartDate and the media streamId.
- Audio resolution follows the public web player (same recipe as
  yt-dlp's VRT extractor): POST an HS256 playerInfo JWT — signed with
  the static key embedded in the public player JS — to the media
  aggregator's tokens endpoint, then GET videos/{streamId}.

VRT serves radio episodes only as HLS/DASH (AAC in MPEG-TS); there is
no MP3. The enclosure therefore uses the HLS playlist URL
(application/vnd.apple.mpegurl) — playable in VLC, AntennaPod and the
Apple ecosystem, but not every podcast client. Enclosure length stays
0 (the playlist size says nothing about the audio).

Usage: python scripts/build_vrt_radio1_duyster_feed.py
Offline/testing env overrides: VRT_DUYSTER_PROGRAM_JSON=<file> (saved
ProgramPage response), VRT_DUYSTER_EPISODES_DIR=<dir> (saved
EpisodePage responses, named <episode-slug>.json),
VRT_DUYSTER_MEDIA_DIR=<dir> (saved media-resolver responses, same
naming). With the dir overrides set no requests are made at all.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import quote, urljoin

from curl_cffi import requests as creq

import common

SHOW_PATH = "/vrtmax/luister/radio/d/duyster~11-177/"
SHOW_URL = "https://www.vrt.be" + SHOW_PATH
OUTPUT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "feeds", "vrt-radio1-duyster.xml")
)
MAX_ITEMS = 100
GRAPHQL_URL = "https://www.vrt.be/vrtnu-api/graphql/public/v1"
TOKENS_URL = (
    "https://media-services-public.vrt.be/vualto-video-aggregator-web"
    "/rest/external/v2/tokens"
)
MEDIA_URL = (
    "https://media-services-public.vrt.be/vualto-video-aggregator-web"
    "/rest/external/v2/videos/{}"
)
# Static player keys embedded in the public VRT web player JS (see also
# yt-dlp's VRT extractor, which documents the same recipe).
PLAYER_KEY_ID = "0-0Fp51UZykfaiCJrfTE3+oMI8zvDteYfPtR+2n1R+z8w="
PLAYER_KEY = "2a9251d782700769fb856da5725daf38661874ca6f80ae7dc2b05ec1a81a24ae"
HLS_MIME = "application/vnd.apple.mpegurl"

DESCRIPTION = (
    "DUYSTER. met Ayco Duyster op VRT Radio 1: muziek voor het late uur. "
    "Alle uitzendingen via VRT MAX."
)
IMAGE = "https://images.vrt.be/orig/2025/02/05/c26e5909-134d-4fe2-9e44-0e68c6d9f700.png"

PROGRAM_QUERY = "query ProgramPage($pageId:ID!,$lazyItemCount:Int = 10,$after:ID,$before:ID,$includeActionItems:Boolean = false){page(id:$pageId){...on ProgramPage{...programPageFragment menu{...tabMenuFragment}components{__typename...on IComponent{...componentTrackingDataFragment}...containerNavigationComponentsFragment...on ContainerNavigation{__typename objectId accessibilityTitle navigationType items{objectId title active components{...containerNavigationComponentsFragment...on ContainerNavigation{__typename objectId accessibilityTitle navigationType items{objectId title components{...containerNavigationComponentsFragment}}}}}}}}...on PodcastProgramPage{...programPageFragment menu{...tabMenuFragment}}...on RadioProgramPage{...programPageFragment menu{...tabMenuFragment}}...errorFragment}}fragment programPageFragment on IPage{objectId permalink header{...pageHeaderFragment}popUp:nudge{...popupFragment}toast:nudge{...toastFragment}seo{...seoFragment}socialSharing{...socialSharingFragment}trackingData{...trackingDataFragment}ldjson}fragment tabMenuFragment on ContainerNavigation{__typename objectId accessibilityTitle navigationType items{__typename objectId title active components{...on ContainerNavigation{__typename objectId accessibilityTitle navigationType items{objectId title components{...containerNavigationComponentsFragment}}}...containerNavigationComponentsFragment}}}fragment containerNavigationComponentsFragment on Component{...on IComponent{__typename...componentTrackingDataFragment}...on Banner{...bannerFragment}...on PaginatedTileList{...paginatedTileListFragment}...on StaticTileList{...staticTileListFragment}...on LazyTileList{objectId title listId}...on Text{...textFragment}...on TagsList{objectId title tags{name title category}}...on PresentersList{objectId title presenters{title type}}...nestedComponentFragment}fragment bannerFragment on Banner{__typename objectId accessibilityTitle brand brandsLogos{brandTitle logos{type colorOnColor width height}}countdown{date}richDescription{__typename text}image{objectId templateUrl alt focusPoint{x y}}title compactLayout textTheme backgroundColor style action{...actionFragment}actionItems{...actionItemFragment}titleArt{objectId templateUrl}labelMeta{__typename type value}secondaryMeta{__typename type value}preview{video{objectId modes{__typename streamId}}}...on IComponent{...componentTrackingDataFragment}}fragment actionFragment on Action{__typename...on FavoriteAction{id favorite title}...on ListDeleteAction{listName id listId title}...on ListTileDeletedAction{listName id listId}...on LinkAction{link internalTarget externalTarget page{__typename...on ProfilePage{flow}}passUserIdentity zone{preferredZone isExclusive}linkTokens{__typename placeholder value}}...on ShareAction{title url}...on SwitchTabAction{referencedTabId link}...on FinishAction{id}...on SubscribeToNewsletterAction{id}}fragment actionItemFragment on ActionItem{__typename objectId accessibilityLabel active mode title themeOverride action{...actionFragment}icons{...iconFragment}}fragment iconFragment on Icon{__typename accessibilityLabel position type...on DesignSystemIcon{value{__typename color name}activeValue{__typename color name}}...on ImageIcon{value{__typename srcSet{src format}}activeValue{__typename srcSet{src format}}}}fragment componentTrackingDataFragment on IComponent{trackingData{data perTrigger{trigger data template{id}}}}fragment nestedComponentFragment on NestedSingleComponentSelect{__typename objectId maxAge title accessibilityTitle options{__typename objectId label isActive nodes{__typename objectId lazyComponentId label preloadedComponent{__typename...on PaginatedTileList{...basicPaginatedTileListFragment}...on StaticTileList{...basicStaticTileListFragment}}}}}fragment basicPaginatedTileListFragment on PaginatedTileList{__typename objectId listId bannerSize description displayType maxAge tileVariant tileContentType title paginatedItems(first:$lazyItemCount,after:$after,before:$before){__typename edges{__typename cursor node{__typename...tileFragment}}pageInfo{__typename endCursor hasNextPage hasPreviousPage startCursor}}...on IComponent{...componentTrackingDataFragment}}fragment tileFragment on Tile{...on IIdentifiable{__typename objectId}...on IComponent{...componentTrackingDataFragment}...on ITile{title active accessibilityTitle componentId tileType action{__typename...on LinkAction{internalTarget link internalTarget externalTarget zone{preferredZone isExclusive}}}actionItems @include(if:$includeActionItems){...actionItemFragment}image{...imageFragment}primaryMeta{...metaFragment}secondaryMeta{...metaFragment}indexMeta{__typename type value}status{accessibilityLabel icon{...iconFragment}text{small default}}labelMeta{__typename type value}}...on ContentTile{brand brandLogos{...brandLogosFragment}}...on BannerTile{backgroundColor brand compactLayout description actionItems{...actionItemFragment}preview{__typename video{objectId modes{__typename streamId}}}textTheme titleArt{objectId templateUrl}}...on EpisodeTile{description chapterStart progress{completed progressInSeconds durationInSeconds}}...on PodcastEpisodeTile{description progress{completed progressInSeconds durationInSeconds}}...on AudioLivestreamTile{brand brandsLogos{brand brandTitle logos{...brandLogosFragment}}description actionItems{...actionItemFragment}progress{durationInSeconds progressInSeconds}tertiaryMeta{...metaFragment}}...on LivestreamTile{description progress{durationInSeconds progressInSeconds}}...on ButtonTile{mode icons{...iconFragment}}...on RadioEpisodeTile{description progress{completed progressInSeconds durationInSeconds}}...on RadioFragmentTile{progress{completed progressInSeconds durationInSeconds}}...on SongTile{startDate formattedStartDate endDate description}...on TopicTile{brandsLogos{brand brandTitle logos{...brandLogosFragment}badge{...imageFragment}}buttons{...actionItemFragment}description}}fragment brandLogosFragment on Logo{colorOnColor height mono primary type width}fragment imageFragment on Image{__typename objectId alt focusPoint{x y}templateUrl}fragment metaFragment on MetaDataItem{__typename type value shortValue longValue icons{...iconFragment}}fragment basicStaticTileListFragment on StaticTileList{__typename objectId listId bannerSize displayType maxAge tileVariant tileContentType title items{...tileFragment}...on IComponent{...componentTrackingDataFragment}}fragment paginatedTileListFragment on PaginatedTileList{__typename objectId listId action{...on LinkAction{__typename externalTarget link}...on SwitchTabAction{__typename link referencedTabId}}banner{actionItems{...actionItemFragment}backgroundColor compactLayout description labelMeta{__typename type value}image{...imageFragment}titleArt{...imageFragment}textTheme title...on IComponent{...componentTrackingDataFragment}}bannerSize displayType maxAge tileVariant paginatedItems(first:$lazyItemCount,after:$after,before:$before){__typename edges{__typename cursor node{__typename...tileFragment...on ComponentTile{component{...on Spotlight{__typename objectId title spotlight{...tileFragment}actionItems{...actionItemFragment}extra{...on PaginatedTileList{...basicPaginatedTileListFragment}...on SpotlightNudge{__typename nudgeObjectId:objectId nudgeTitle:title nudgeDescription:description button{...actionItemFragment}nudgeTrackingData:trackingData{...trackingDataFragment}}}brand trackingData{...trackingDataFragment}}}}}}pageInfo{__typename endCursor hasNextPage hasPreviousPage startCursor}}tileContentType title description...on IComponent{...componentTrackingDataFragment}}fragment trackingDataFragment on PageTrackingData{data perTrigger{trigger data template{id}}}fragment staticTileListFragment on StaticTileList{__typename objectId listId title description tileContentType displayType maxAge tileVariant action{...on LinkAction{__typename externalTarget internalTarget link}...on SwitchTabAction{__typename link referencedTabId}}banner{actionItems{...actionItemFragment}description image{...imageFragment}labelMeta{__typename type value}compactLayout backgroundColor textTheme title titleArt{objectId templateUrl}...on IComponent{...componentTrackingDataFragment}}bannerSize items{...tileFragment}...on IComponent{...componentTrackingDataFragment}}fragment textFragment on Text{__typename objectId html}fragment pageHeaderFragment on PageHeader{objectId accessibilityTitle brandsLogos{brandTitle}presenters{title}title titleArt{objectId templateUrl}richDescription{__typename html}actionItems{...actionItemFragment}primaryMeta{type value shortValue}secondaryMeta{type value shortValue longValue}tertiaryMeta{type value shortValue}image{__typename objectId focusPoint{x y}templateUrl}}fragment seoFragment on SeoProperties{__typename title description}fragment socialSharingFragment on SocialSharingProperties{__typename title description image{__typename objectId templateUrl}}fragment popupFragment on PopUp{__typename brand brandsLogos{...brandLogo}buttons{...actionItemFragment}description image{...imageFragment}objectId size status{text{default small}icon{...iconFragment}}title videoStreamId trackingData{...trackingDataFragment}}fragment brandLogo on BrandLogo{brand brandTitle logos{type primary colorOnColor}}fragment toastFragment on Toast{__typename description image{...imageFragment}objectId title}fragment errorFragment on ErrorPage{errorComponents:components{...noContentFragment}trackingData{...trackingDataFragment}}fragment noContentFragment on NoContent{__typename objectId title text backgroundImage{...imageFragment}mainImage{...imageFragment}noContentType actionItems{...actionItemFragment}variant isResponsive}"

EPISODE_QUERY = "query EpisodePage($pageId:ID!){page(id:$pageId){...on PlaybackPage{...playbackPageFragment}...on RadioEpisodePage{header{title announcementValue brandsLogos{brandTitle logos{type mono width height}}}}...errorFragment}}fragment playbackPageFragment on PlaybackPage{__typename objectId title brand permalink seo{...seoFragment}socialSharing{...socialSharingFragment}trackingData{...trackingDataFragment}ldjson player{...playerFragment}menu{...menuFragment}popUp:nudge{...popupFragment}toast:nudge{...toastFragment}components{...bannerFragment...contactInfoFragment...mediaInfoFragment}}fragment menuFragment on ContainerNavigation{__typename objectId accessibilityTitle items{__typename objectId componentId title active action{...on SwitchTabAction{__typename referencedTabId link}}}}fragment seoFragment on SeoProperties{__typename title description}fragment socialSharingFragment on SocialSharingProperties{__typename title description image{__typename objectId templateUrl}}fragment playerFragment on MediaPlayer{__typename objectId classification{iconName}highlight{__typename title description}maxAge image{...imageFragment}modes{__typename active adsUrl cimMediaTrackingData{__typename channel ct programDuration programId programName programSeason publicationDate seriesName se st tv vf}mediaTrackingData{...trackingDataFragment}token{placeholder value}resumePointTemplate{mediaId mediaName}streamId...on VideoPlayerMode{aspectRatio markers{__typename title description icon{__typename...on ImageIcon{value{srcSet{src}}}}...on MediaPlayerHighlightMarker{spoiler startOffsetInSeconds}}}...on AudioPlayerMode{broadcastStartDate}}progress{__typename completed durationInSeconds progressInSeconds}secondaryMeta{...metaFragment}subtitle title}fragment imageFragment on Image{__typename objectId alt focusPoint{x y}templateUrl}fragment metaFragment on MetaDataItem{__typename type value shortValue longValue icons{...iconFragment}}fragment iconFragment on Icon{__typename accessibilityLabel position type...on DesignSystemIcon{value{__typename color name}activeValue{__typename color name}}...on ImageIcon{value{__typename srcSet{src format}}activeValue{__typename srcSet{src format}}}}fragment trackingDataFragment on PageTrackingData{data perTrigger{trigger data template{id}}}fragment bannerFragment on Banner{__typename objectId accessibilityTitle brand brandsLogos{brandTitle logos{type colorOnColor width height}}countdown{date}richDescription{__typename text}image{objectId templateUrl alt focusPoint{x y}}title compactLayout textTheme backgroundColor style action{...actionFragment}actionItems{...actionItemFragment}titleArt{objectId templateUrl}labelMeta{__typename type value}secondaryMeta{__typename type value}preview{video{objectId modes{__typename streamId}}}...on IComponent{...componentTrackingDataFragment}}fragment actionFragment on Action{__typename...on FavoriteAction{id favorite title}...on ListDeleteAction{listName id listId title}...on ListTileDeletedAction{listName id listId}...on LinkAction{link internalTarget externalTarget page{__typename...on ProfilePage{flow}}passUserIdentity zone{preferredZone isExclusive}linkTokens{__typename placeholder value}}...on ShareAction{title url}...on SwitchTabAction{referencedTabId link}...on FinishAction{id}...on SubscribeToNewsletterAction{id}}fragment actionItemFragment on ActionItem{__typename objectId accessibilityLabel active mode title themeOverride action{...actionFragment}icons{...iconFragment}}fragment componentTrackingDataFragment on IComponent{trackingData{data perTrigger{trigger data template{id}}}}fragment contactInfoFragment on ContactInfo{__typename title items{title description options{objectId title icons{...iconFragment}action{...on LinkAction{link externalTarget}}}}}fragment mediaInfoFragment on MediaInfo{__typename objectId title maxAge description accessibilityTitle actionItems{...actionItemFragment}trackingData{...trackingDataFragment}image{...imageFragment}primaryMeta{...metaFragment}secondaryMeta{...metaFragment}tertiaryMeta{...metaFragment}quaternaryMeta{label...metaFragment}}fragment popupFragment on PopUp{__typename brand brandsLogos{...brandLogo}buttons{...actionItemFragment}description image{...imageFragment}objectId size status{text{default small}icon{...iconFragment}}title videoStreamId trackingData{...trackingDataFragment}}fragment brandLogo on BrandLogo{brand brandTitle logos{type primary colorOnColor}}fragment toastFragment on Toast{__typename description image{...imageFragment}objectId title}fragment errorFragment on ErrorPage{errorComponents:components{...noContentFragment}trackingData{...trackingDataFragment}}fragment noContentFragment on NoContent{__typename objectId title text backgroundImage{...imageFragment}mainImage{...imageFragment}noContentType actionItems{...actionItemFragment}variant isResponsive}"

log = logging.getLogger("vrt_duyster_feed")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _slug(link: str) -> str:
    """Episode path segment of an episode URL, e.g. duyster~11-39811-0."""
    return link.rstrip("/").rsplit("/", 1)[-1]


def _decoded_blob(text: str) -> str:
    """Concatenated base64 segments embedded in VRT's opaque objectIds.

    Tab objectIds hide their kind inside such blobs: "|recent|" for
    available broadcasts, "|upcoming|" for scheduled ones.
    """
    parts = []
    for match in re.finditer(r"[A-Za-z0-9+/=]{20,}", text or ""):
        try:
            decoded = base64.b64decode(match.group(0) + "==", validate=False)
        except Exception:  # noqa: BLE001
            continue
        parts.append(decoded.decode("utf-8", "replace"))
    return "".join(parts)


# --------------------------------------------------------------------------
# GraphQL
# --------------------------------------------------------------------------

def graphql(operation: str, variables: dict, query: str) -> dict:
    r = creq.post(
        GRAPHQL_URL,
        json={"operationName": operation, "variables": variables, "query": query},
        impersonate="chrome",
        timeout=30,
        headers={
            "Content-Type": "application/json",
            # required — the API answers 400 without a client name
            "X-VRT-CLIENT-NAME": "vrtnu-web",
            "X-VRT-CLIENT-VERSION": "1.0",
        },
    )
    r.raise_for_status()
    payload = r.json()
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"GraphQL {operation} error: {errors}")
    return payload


def fetch_program_json() -> dict:
    """Episode tile list of the Duyster program page."""
    return graphql(
        "ProgramPage",
        {"pageId": SHOW_PATH, "lazyItemCount": MAX_ITEMS, "includeActionItems": False},
        PROGRAM_QUERY,
    )


def fetch_episode_json(link: str) -> dict:
    """Episode page data for one episode URL (kept separate for tests)."""
    page_id = SHOW_PATH + _slug(link) + "/"
    return graphql("EpisodePage", {"pageId": page_id}, EPISODE_QUERY)


# --------------------------------------------------------------------------
# Media resolution
# --------------------------------------------------------------------------

def jwt_hs256(payload: dict, key: str = PLAYER_KEY, key_id: str = PLAYER_KEY_ID) -> str:
    def b64(obj: dict) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    signing_input = f"{b64(header)}.{b64(payload)}"
    signature = hmac.new(key.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def fetch_player_token() -> str:
    """vrtPlayerToken for the media aggregator (public player recipe)."""
    player_info = {
        "platform": "desktop",
        "app": {"type": "browser", "name": "Chrome"},
        "device": "undefined (undefined)",
        "os": {"name": "Linux", "version": ""},
        "player": {
            "name": "VRT web player",
            "version": "5.1.1-prod-2025-02-14T08:44:16",
        },
        "exp": round(time.time(), 3) + 900,
    }
    r = creq.post(
        TOKENS_URL,
        json={"identityToken": "", "playerInfo": jwt_hs256(player_info)},
        impersonate="chrome",
        timeout=30,
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    return r.json()["vrtPlayerToken"]


def fetch_media_json(stream_id: str) -> dict:
    """Media-resolver response (playable target URLs) for a streamId."""
    url = MEDIA_URL.format(quote(stream_id, safe=""))
    r = creq.get(
        url,
        params={"vrtPlayerToken": fetch_player_token(), "client": "null"},
        impersonate="chrome",
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def resolve_audio(media: dict) -> dict | None:
    """HLS target URL + MIME type from a media-resolver response."""
    for target in media.get("targetUrls") or []:
        if str(target.get("type")).lower() == "hls" and target.get("url"):
            return {"url": target["url"], "type": HLS_MIME}
    return None


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def parse_program(data: dict) -> list[dict]:
    """Episode entries from the ProgramPage response.

    Tiles come newest-first; the exact broadcast date is unknown until
    the episode page is fetched (published starts as None).
    """
    page = (data.get("data") or {}).get("page") or {}
    menu = page.get("menu") or {}
    items = []
    seen = set()
    for tab in menu.get("items") or []:
        if "|upcoming|" in _decoded_blob(tab.get("objectId") or ""):
            # "Geplande uitzendingen": scheduled broadcasts, no audio yet
            continue
        for component in tab.get("components") or []:
            if not isinstance(component, dict) or (
                component.get("__typename") != "PaginatedTileList"
            ):
                continue
            for edge in (component.get("paginatedItems") or {}).get("edges") or []:
                node = edge.get("node") or {}
                if node.get("__typename") != "RadioEpisodeTile":
                    continue
                link = urljoin(SHOW_URL, (node.get("action") or {}).get("link") or "")
                if not link.startswith(SHOW_URL) or link in seen:
                    continue
                seen.add(link)
                items.append(
                    {
                        "id": link,
                        "title": _norm(node.get("title") or ""),
                        "link": link,
                        "description": _norm(node.get("description") or ""),
                        "published": None,
                        "image": (node.get("image") or {}).get("templateUrl") or "",
                    }
                )
    if not items:
        raise ValueError(
            "no episode tiles parsed — VRT MAX page layout may have changed"
        )
    log.info("parsed %d episode tile(s)", len(items))
    return items


def parse_episode(data: dict) -> dict:
    """Exact date, title and streamId from an EpisodePage response."""
    page = (data.get("data") or {}).get("page") or {}
    player = page.get("player")
    if not isinstance(player, dict) or not player.get("modes"):
        raise ValueError(
            "no player modes — VRT MAX episode layout may have changed"
        )

    broadcast_start = None
    stream_id = None
    for mode in player["modes"]:
        if not isinstance(mode, dict):
            continue
        start = mode.get("broadcastStartDate")
        if start and broadcast_start is None:
            broadcast_start = datetime.fromisoformat(start)
        stream_id = stream_id or mode.get("streamId")

    title = (page.get("seo") or {}).get("title") or ""
    suffix = " | VRT MAX"
    if title.endswith(suffix):
        title = title[: -len(suffix)]

    description = ""
    for component in page.get("components") or []:
        if (
            isinstance(component, dict)
            and component.get("__typename") == "MediaInfo"
            and component.get("description")
        ):
            description = component["description"]
            break

    return {
        "broadcast_start": broadcast_start,
        "stream_id": stream_id,
        "title": _norm(title),
        "description": _norm(description),
    }


# --------------------------------------------------------------------------
# Enrichment
# --------------------------------------------------------------------------

def _read_local(path: str | None) -> dict | None:
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def enrich_items(items: list[dict], previous: dict[str, dict]) -> None:
    """Attach exact dates, titles and audio enclosures to items.

    Items whose previous entry already carries an enclosure are not
    fetched again. With VRT_DUYSTER_EPISODES_DIR / VRT_DUYSTER_MEDIA_DIR
    set, only saved JSON copies are used (offline mode — no requests).
    """
    by_id = {entry["id"]: entry for entry in previous.values()}
    enriched = 0
    for item in items:
        old = by_id.get(item["id"])
        if old and old.get("enclosure"):
            item["enclosure"] = old["enclosure"]
            if old.get("published"):
                item["published"] = old["published"]
            if old.get("title"):
                item["title"] = old["title"]
            if old.get("description"):
                item["description"] = old["description"]
            continue

        episode = None
        if os.environ.get("VRT_DUYSTER_EPISODES_DIR"):
            path = os.path.join(
                os.environ["VRT_DUYSTER_EPISODES_DIR"], _slug(item["link"]) + ".json"
            )
            episode = _read_local(path)
        else:
            try:
                episode = fetch_episode_json(item["link"])
            except Exception as exc:  # noqa: BLE001
                log.warning("could not fetch %s: %s", item["link"], exc)
        if not episode:
            continue
        parsed = parse_episode(episode)
        if parsed["broadcast_start"]:
            item["published"] = parsed["broadcast_start"]
        if parsed["title"]:
            item["title"] = parsed["title"]
        if parsed["description"]:
            item["description"] = parsed["description"]

        if not parsed["stream_id"]:
            continue
        media = None
        if os.environ.get("VRT_DUYSTER_MEDIA_DIR"):
            path = os.path.join(
                os.environ["VRT_DUYSTER_MEDIA_DIR"], _slug(item["link"]) + ".json"
            )
            media = _read_local(path)
        else:
            try:
                media = fetch_media_json(parsed["stream_id"])
            except Exception as exc:  # noqa: BLE001
                log.warning("could not resolve audio for %s: %s", item["link"], exc)
        if not media:
            continue
        audio = resolve_audio(media)
        if audio:
            item["enclosure"] = {**audio, "length": 0}
            enriched += 1
    log.info("resolved audio for %d item(s)", enriched)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def load_program_data() -> dict | None:
    path = os.environ.get("VRT_DUYSTER_PROGRAM_JSON")
    if path:
        log.info("using local program JSON copy: %s", path)
        return _read_local(path)
    return fetch_program_json()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    kwargs = dict(
        feed_id=SHOW_URL,
        title="Duyster (VRT Radio 1)",
        link=SHOW_URL,
        description=f"{DESCRIPTION} (auto-generated from {SHOW_URL})",
        language="nl",
        itunes_author="VRT Radio 1",
        itunes_summary=DESCRIPTION,
        itunes_image=IMAGE,
        itunes_category="Music",
        itunes_explicit="no",
    )

    try:
        data = load_program_data()
        if data is None:
            raise RuntimeError("no program data loaded")
        items = parse_program(data)
    except Exception as exc:  # noqa: BLE001
        return common.write_warning_feed(
            OUTPUT_PATH, MAX_ITEMS, SHOW_URL, exc, **kwargs
        )

    previous = common.load_previous(OUTPUT_PATH)
    enrich_items(items, previous)
    merged = common.merge_items(common.without_warning(previous), items)
    common.write_feed(list(merged.values()), OUTPUT_PATH, MAX_ITEMS, **kwargs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
