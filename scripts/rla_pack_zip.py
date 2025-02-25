import argparse, os, logging, coloredlogs, io

from sssekai.fmt.rla import decode_buffer_base64, read_rla_frames

MAGNITUDE = 1e7
SEGMENTS_PER_CLIP = 30

logger = logging.getLogger("sssekai")
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Packages loose SSE Motion packets into an archival format (zip) for loading into Blender"
    )
    parser.add_argument("indir", help="Directory containing SSE packets")
    parser.add_argument("outfile", help="Output zipfile name")
    parser.add_argument("--version", help="RLA version to use", default="1.6", type=str)
    parser.add_argument(
        "--skip-validation", help="Skip validation of SSE packets", action="store_true"
    )
    args = parser.parse_args()

    coloredlogs.install(level="DEBUG", logger=logger)
    logger.debug("Loading SSE packets from %s", args.indir)
    raw_data = list()
    if args.skip_validation:
        logger.warning("Skipping validation of SSE packets. Reading as-is.")
    else:
        logger.info("Validating SSE packets")
    dropped = 0
    ls = os.listdir(args.indir)
    for f in ls:
        data = open(os.path.join(args.indir, f), "rb").read()
        if args.skip_validation:
            raw_data.append((f, data))
        else:
            try:
                decode_buffer_base64(data)
                raw_data.append((f, data))
            except Exception as e:
                logger.error("Failed to decode %s: %s", f, e)
                dropped += 1
            finally:
                if raw_data:
                    print(
                        "read: %8d drop: %8d, health: %.2f%%, total: %8d"
                        % (
                            len(raw_data),
                            dropped,
                            100 * (1 - dropped / len(raw_data)),
                            len(ls),
                        ),
                        end="\r",
                    )
    version = tuple(map(int, args.version.split(".")))
    frame_gen = read_rla_frames(
        raw_data,
        version,
    )
    logger.debug("Locating first Motion frame")
    mot = next(filter(lambda x: x[1]["type"] == "MotionCaptureData", frame_gen), None)
    assert mot, "No MotionCaptureData found in SSE packets"
    base_tick = int(mot[0].split("-")[0])
    base_frame_tick = min((data["timestamp"] for data in mot[1]["data"]))
    logger.info("Base tick: %d", base_tick)
    logger.info("Packing into ZIP")

    rla_stream = io.BytesIO()
    num_segments = 0

    write_int = lambda value, nbytes: rla_stream.write(value.to_bytes(nbytes, "little"))
    write_buffer = lambda value: rla_stream.write(value)

    segments = []
    for fname, data in raw_data:
        tick = int(fname.split("-")[0])
        split, _, _ = decode_buffer_base64(data)
        frame_tick = base_frame_tick + (tick - base_tick) / 1000 * MAGNITUDE
        write_int(int(frame_tick), 8)
        write_int(len(data), 4)
        write_buffer(data)
        num_segments += 1
        if num_segments >= SEGMENTS_PER_CLIP and split is None:
            num_segments = 0
            segments.append(bytes(rla_stream.getbuffer()))
            rla_stream = io.BytesIO()
    if num_segments > 0:
        segments.append(bytes(rla_stream.getbuffer()))
    logger.info("Writing %d segments to %s", len(segments), args.outfile)
    rlh_header = {
        "baseTicks": base_frame_tick,
        "version": args.version,
        "splitSeconds": 0,
        "splitFileIds": list(range(len(segments))),
    }

    import zipfile, json

    with zipfile.ZipFile(args.outfile, "w") as z:
        z.writestr("sekai.rlh", json.dumps(rlh_header))
        for idx, segment in enumerate(segments):
            print(
                "* packing %s %08d/%08d" % ("/|-"[idx % 3], idx, len(segments)),
                end="\r",
            )
            z.writestr("sekai_%02d_%08d.rla" % (0, idx), segment)
