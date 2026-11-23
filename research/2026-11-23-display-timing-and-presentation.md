# League frame pacing at 120 Hz

The player reported steadier lows across two successive changes to the experimental runtime. The last reported range was 60–70 FPS. The earlier peak of about 120 FPS remained out of reach. The two fixes were subsequently extracted onto `main` at `75d1bf6` so they can be evaluated without the other experiments.

## Manual play observations

The player compared the same setup and scene with a 120 Hz monitor, an in-game cap of 240 FPS, and VSync disabled. FPS varied with the scene. The figures below are approximate readings from play. No frame-time percentiles or match averages were collected for this comparison.

| Build played | Reported FPS |
| --- | --- |
| Earlier reference on the same setup | Peak around 120, lows around 40–50 |
| Accumulated rendering and runtime experiments | Peak around 60, lows around 20–30 |
| Experimental build with the QuartzCore presentation fix | 40–70 |
| Same series with the CoreVideo timing fix added | Stable around 60–70, with shallower drops |

The broader experiments included Metal binding deduplication, Indium render-pass and drawable-copy changes, X11 child-window mapping, and darlingserver send handling. They were changed across builds, so the regression cannot be assigned to any one of them from these observations. The CoreVideo-only checkout has no separately reported play result in this series.

## Clean two-fix baseline

The player confirmed that the 14:07 match on November 23 used the clean pair on `75d1bf6`. The earlier matches that day have uncertain build attribution. The existing post-match tool measured 61.3 FPS across the match and 51.9 FPS across its slowest quarter. Its nearest-rank median and p95 were 16.63 and 19.72 ms across ten-second averages. Individual frame times and fight timestamps are unavailable for this match.

Indium also wrote 74 submission summaries between 14:08 and 14:28, all with batching enabled. Each row covers 1,024 presentations. For adjacent rows, elapsed monotonic time divided by 1,024 gives the mean presentation interval for the block ending at the later row. Excluding intervals starting within 90 seconds of the first row leaves 64 blocks. The table shows medians over the 16 fastest and 16 slowest blocks.

| Blocks | Presentation interval | Command-buffer commits per presentation | Vulkan submits per presentation |
| --- | ---: | ---: | ---: |
| Fastest quarter | 13.62 ms | 11.68 | 2.21 |
| Slowest quarter | 18.88 ms | 18.59 | 3.16 |

Submission volume rose in slower blocks. The counters lack a process ID and phase durations. They support investigating submission cost alongside CPU scheduling and presentation waits. They cannot attribute the 5.26 ms difference to submissions or identify which blocks contained fights.

## Diagnostic match at 14:59

The player described action throughout the match and did not mark individual fights. The post-match summary reported 66.0 FPS overall and 55.5 FPS across the slowest quarter, compared with 61.3 and 51.9 in the 14:07 baseline. The 14:59 match had six startup samples with the game clock frozen near zero. Restricting both matches to samples after game time 1 s gives 63.3 and 60.9 FPS respectively. These were two matches on the same build.

The player identified the physical GPU as an AMD Radeon RX 9070 XT. Darling's compatibility profile presents an AMD Radeon Pro 5500M to the guest. The host sampler read the physical RX 9070 XT's Linux `gpu_busy_percent` counter once per second until the game exited. [Hardware presentation profile](../docs/PLATFORM_IDENTITY.md#hardware-presentation-profile)

Matching those readings and the game process leader's Linux scheduler counters to the Indium block timestamps gives 61 complete blocks after warmup, spanning about 16 minutes. The GPU averaged 99.7% busy and reached at least 90% in 974 of 976 samples. During that span the process leader ran for 29.3% of elapsed time and spent 2.8% runnable while waiting for a CPU. The remainder includes time blocked or sleeping. The scheduler counters do not identify the wait.

| Blocks ranked by presentation interval | Median interval | Commits per presentation | Submits per presentation | GPU busy |
| --- | ---: | ---: | ---: | ---: |
| Fastest 15 | 13.32 ms | 9.40 | 2.21 | 100.0% |
| Slowest 15 | 17.57 ms | 16.80 | 2.89 | 99.8% |

Each table entry is the median of its block values. GPU busy is device-wide. The joint observations make GPU work during rendering and presentation the first area to investigate. CPU scheduling delay on the process leader was small. The measurements cannot divide GPU work between the game, Darling's presentation path and other GPU users, or attribute the slower blocks to a particular rendering operation.

The guest frame-phase CSVs and wait summaries were absent. The two diagnostic markers had been created before launch. Darling clears the guest temporary directory at startup. For a timing run, enable the markers **after the Riot Client is open and before the game starts**, from inside the running guest. Verify that the runtime writes the wait-counter activation line and the first frame-phase files during the match. [Setup instructions](../docs/SETUP.md)

## Instrumented match at 15:46

The player reported smoother play and unchanged settings. The clean two-fix build averaged 106.4 FPS, with 83.7 FPS across its slowest quarter. The earlier matches averaged 61.3 and 66.0 FPS. Excluding samples at game time 1 s or earlier gives 105.2, 60.9 and 63.3 FPS for the 15:46, 14:07 and 14:59 matches respectively. Startup samples therefore do little to explain the difference. This was a fresh match with timing enabled, without an intervening optimization.

QuartzCore recorded 16,384 complete queued presentations from 15:48:13 through 15:51:01. Within each of its eight capture files, split the ordered requests into consecutive groups of 128. Rank the 128 groups by mean time between requests and compare the fastest and slowest 32. Entries below are medians of group means.

| Measured time (ms) | Fastest quarter | Slowest quarter |
| --- | ---: | ---: |
| Interval between presentation requests | 7.61 | 12.71 |
| Queued until main-thread render callback starts | 0.30 | 0.35 |
| Render call on the main thread | 0.06 | 0.07 |
| Queued-presentation flush on the main thread | 3.23 | 6.46 |

Across all captured requests the flush took 4.99 ms at the median and 7.46 ms at p95. In all 16,376 adjacent pairs within the capture files, the next request was queued after the previous flush returned. The flush includes attaching the context and window, applying the swap interval, calling `CGLFlushDrawable` and restoring the previous context when needed. Its elapsed time can include waiting for GPU work issued earlier. The render call measures elapsed CPU-side time and leaves GPU work asynchronous.

Indium recorded 4,096 presenting command buffers during the first 49 seconds of the QuartzCore capture. The median from its worker-side commit timestamp to submission was 0.072 ms. The median from submission to completion callback was 18.80 ms over 4,095 complete observations. Completion can overlap subsequent frames. The separate five-second wait summaries recorded 105.84 cumulative seconds in `drain@commit` across 152,576 calls (0.69 ms per recorded call). These measurements cover different spans and must not be added to the flush time.

Across 1,251 host samples in the post-warmup submission blocks, the physical RX 9070 XT averaged 99.2% busy. It had averaged 99.7% in the slower 14:59 match. Both could keep the GPU busy while producing different numbers of frames. The detailed timings identify the main-thread flush as a place where the game spends more wall time in slower stretches of this capture. They do not explain the FPS difference between matches, identify the GPU operation responsible, or establish how much flush time is recoverable.

## Search for implementation changes

Indium records its submission timestamp before calling the drawable's `present()` and its presentation timestamp after the call. QuartzCore records the enqueue time inside that call. In the overlapping 49-second capture, 4,093 completed Indium records bracketed exactly one QuartzCore enqueue each, all distinct. For 4,019 of those records (98.2%), the main-thread flush returned within 1 ms of the **preceding presenting buffer's** completion callback. For 3,856 it was within 0.1 ms. The matched buffer's own completion callback followed the flush by a median of 12.02 ms. Indium samples callback execution on its event-loop thread after a timeline semaphore signals. The near-coincidence identifies where to investigate backpressure, but does not establish which operation waited for which.

Two proposed CPU shortcuts already exist. CGL skips `eglMakeCurrent` when the calling thread has the requested context and surface. It also skips `eglSwapInterval` for a successful, unchanged interval request on the current context and invalidates that state when attaching a different surface. QuartzCore already samples the drawable's imported GL texture directly. None of these observations removes the Vulkan transfer into the shared image.

One concrete candidate is the command-buffer commit loop. It calls each referenced texture's `precommit` once per encoder-list occurrence, after encoder recording has finished. The later deduplication for semaphore handling comes too late to affect these calls. For a QuartzCore drawable texture each call records a full-extent filtered blit and two barrier batches. A temporary host fixture compiled the shipped loop with two render encoders and one blit encoder. Referencing drawable A three times and B once produced three calls for A and one for B.

On the physical RX 9070 XT, a headless Vulkan microbenchmark measured a synthetic 1920×1080 optimal BGRA8 to linear RGBA8 blit with layout transitions. With 50 GPU timestamp measurements per case after warmup, one blit took 0.064 ms at the median and three took 0.183 ms. Both produced the expected pixels on readback. This isolates about **0.12 ms** of GPU work for two redundant blits at this size. It excludes GL import, presentation, competing rendering work and the game. The match capture did not count duplicate drawable references or record drawable dimensions.

The narrow candidate is to coalesce repeated preparations of the same QuartzCore drawable texture within a single command buffer, keeping separate drawables, command buffers, image conversions and synchronization intact. Its priority depends on the number of duplicates during play. For a larger gain, the existing Indium render-pass Vulkan timestamp mode can rank GPU work alongside presentation timings. Use aggregate pass timing to identify a specific expensive pass before selecting a broader rendering change.

## Match with drawable copies coalesced at 17:14

The player reported smooth play. The 17:14 match and the 15:46 match before the Indium change both reported the Default map skin and game release 16.23. The two local runs that averaged over 120 FPS on November 21 also used 16.23. Both reported the Tutorial map skin and lasted about eight minutes. The earlier player-reported peak around 120 FPS is a separate observation.

The player identified the November 23 setup as a VM with GPU passthrough over a PCIe x4 link. The planned comparison uses this runtime on a native host with a PCIe x8 link. Both the execution environment and link width change together, so any FPS difference will describe the two setups as a whole.

| Match | Whole-log FPS | Slowest-quarter FPS (whole log) | First eight game minutes, FPS | Slowest quarter of those eight minutes, FPS |
| --- | ---: | ---: | ---: | ---: |
| Nov 21, 15:37, Tutorial | 134.0 | 114.5 | 137.0 | 120.5 |
| Nov 21, 15:46, Tutorial | 135.7 | 103.6 | 139.3 | 108.2 |
| Nov 23, 15:46, Default, before | 106.4 | 83.7 | 102.8 | 82.9 |
| Nov 23, 17:14, Default, after | 104.2 | 78.9 | 96.3 | 79.8 |

The whole-log columns use the existing post-match report. The eight-minute columns use positive frame-time samples with game clock above 1 s through 480 s and sample duration under 20 s. This excludes loading and the final whole-session summary row. Using the same filter through the end of play gives 99.5 FPS for the latest match and 105.6 for the previous one. In the latest match, 23 of 102 gameplay samples exceeded 120 FPS and the slowest ten-second sample averaged 73.0 FPS at game time 15:58.

The existing submission and host monitors covered the lower-FPS periods. Matching 99 complete 1,024-presentation blocks to overlapping gameplay samples and ranking them by game-reported frame time gives the following medians. The wall-clock alignment estimates game time zero from the final sample and file modification time. Moving the alignment three seconds either way preserves the trends.

| Gameplay blocks | Sampled frame time | Commits per presentation | Vulkan submits per presentation | RX 9070 XT busy |
| --- | ---: | ---: | ---: | ---: |
| Fastest quarter | 7.88 ms | 7.56 | 2.06 | 99.9% |
| Slowest quarter | 11.88 ms | 15.23 | 2.90 | 99.3% |

The bounded Indium timing capture ran from 17:16:00 to 17:16:17, before the game clock began advancing around 17:16:30. QuartzCore continued until 17:17:48. For its 128-presentation groups starting at least ten seconds into gameplay, the median flush grew from 3.54 ms in the fastest quarter to 5.02 ms in the slowest. Direct main-thread rendering went from 0.06 to 0.07 ms. The detailed timings therefore cover early play only. The longer capture associates low FPS with increased command-buffer and submission counts on an already busy GPU. It cannot attribute the difference to submission overhead, a particular rendering pass, or the drawable-copy change.

## What the host checks established

- **QuartzCore presentation.** When the main thread runs out of Metal drawables, it can render and flush one inline while its presentation callback is still queued. The callback used to render and swap again. The fix associates each request with a per-layer ticket and records which render reached the window. In the host fixture, an inline swap served the first drawable, its queued callback skipped the duplicate swap, and the second drawable still received its own swap. The checks also covered nested layers, a failed swap, and a slot reused after resize. [QuartzCore patch](../patches/cocotron.patch)
- **CoreVideo timing.** With `RCLOL_REFRESH_HZ=120`, two callbacks 8.33 ms apart could report the same video frame. The predicted output was 16.67 ms ahead, and `CVDisplayLinkGetCurrentTime` reported a scale of 60. The pump, callback timestamps, and current-time query now share one refresh setting and Mach timebase conversion. The host fixture verified the 8.33 ms prediction at 120 Hz, other refresh rates, and the 60 Hz fallback. [CoreVideo patch](../patches/darling.patch)

## Hardware scope and performance limits

The presentation-ticket and drawable-preparation changes contain no GPU-vendor
condition. They remove work only when an inline presentation has already served
a queued callback, or when one command buffer references the same drawable more
than once. A workload without those cases gains nothing from those removals and
still pays the tracking overhead. The CoreVideo correction aligns timestamps
with the configured refresh rate; the rate mismatch it corrects occurs away
from 60 Hz. It uses one process-wide integer refresh setting, so it does not
establish correct timing for mixed-refresh monitors or physical VRR.

The measured 0.12 ms saving applies to the synthetic duplicate-blit workload on
the tested GPU. Its size on other GPUs, drivers, resolutions and memory systems
is unmeasured. Saving GPU work can improve frame rate when that work limits frame
completion, but CPU limits, a frame cap, VSync or compositor pacing can hide it.
The recorded 106.4 versus 104.2 FPS matches establish neither a speedup nor a
regression because they were separate, uncontrolled matches. These are portable
optimization mechanisms with conditional benefits; universal hardware
compatibility and a gameplay performance gain remain unverified. The planned VM
PCIe x4 versus native PCIe x8 comparison also changes multiple factors at once.

## Remaining performance question

The next investigation should separate context attachment, swap-interval setup, buffer swap and context restoration inside the queued-presentation flush. In particular, distinguish repeated CPU work from backpressure due to previously submitted GPU work before changing that path. Preserve drawable ownership, synchronization, resize handling and the current hardware presentation. Empty-pass framebuffer creation remains an unmeasured candidate.

For a diagnostic match, use the same clean build, compatibility profile, graphics settings, 120 Hz refresh, 240 FPS cap and disabled VSync. Mark a quiet stretch and a sustained fight by game clock if practical. Enable the existing `metal-frame-interval-capture` and `metal-debug-waits` markers using the startup order above. Both timing recorders skip the first 90 seconds. Indium records 4,096 presenting buffers and QuartzCore records eight blocks of 2,048 requests, so later fights can fall outside their coverage. The wait summaries and passive host CPU, run-queue and GPU measurements can cover the entire match.

Compare overlapping time windows. Measure queue delay, composite and flush time separately on complete QuartzCore rows. Inspect Indium commit-to-submit timing and the five-second wait summaries alongside per-thread CPU and run-queue time. Treat missing phases as missing data and overlapping work as concurrent. Select a runtime change only when a measured cost accounts for time on the game's frame path.

Disable the diagnostic markers before starting the ordinary comparison runs. Compare the candidate with the clean pair using average FPS, slowest-quarter FPS and the player's observations in action. Repeat comparable matches if the result falls within match variation. Verify rendering, input, match completion and return to the client on the candidate.
