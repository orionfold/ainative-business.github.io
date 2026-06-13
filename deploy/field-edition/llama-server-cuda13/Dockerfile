# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
#
# ghcr.io/orionfold/llama-server-cuda13 — the Arena Field Edition serving lane.
#
# A llama.cpp `llama-server` built for CUDA 13.0 / SM121 (the GB10 in the DGX
# Spark, compute capability 12.1). There is no aarch64+CUDA-13 prebuilt wheel
# for the runtimes the open stack would otherwise use, so the §5 packaging ships
# a prebuilt container instead (see _SPECS/arena-field-edition-v1.md §5/§7).
#
# Pinned to llama.cpp b9128 (856c3adac1709be15e1ea2529a0e89f742d25fe0) — the
# exact build proven on the dogfood box (`llama-server --version` → build 856c3ad).
# Re-pin LLAMA_CPP_REF + the base-image digests per the §9 quarterly proven-matrix
# cadence; `fieldkit field-edition update` re-runs the §8 gate after any bump.
#
# Build (on the Spark; needs the Container Toolkit for the buildx CUDA arch):
#   docker build --build-arg LLAMA_CPP_REF=856c3ada... \
#     -t ghcr.io/orionfold/llama-server-cuda13:0.1 \
#     deploy/field-edition/llama-server-cuda13
#
# `libcuda.so.1` (the driver) is NOT bundled — the NVIDIA Container Toolkit
# injects it at `docker run --gpus all` / the Compose `deploy.reservations` block
# the bundle renders (compose.py:_gpu_reservation).

ARG CUDA_TAG=13.0.1
FROM nvidia/cuda:${CUDA_TAG}-devel-ubuntu24.04 AS build

ARG LLAMA_CPP_REF=856c3adac1709be15e1ea2529a0e89f742d25fe0
# GB10 = compute capability 12.1 → CUDA arch 121.
ARG CUDA_ARCH=121

RUN apt-get update && apt-get install -y --no-install-recommends \
        git cmake ninja-build build-essential libcurl4-openssl-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone https://github.com/ggml-org/llama.cpp.git . \
    && git checkout ${LLAMA_CPP_REF}

# The build container has no NVIDIA driver, so the CUDA *driver* API symbols
# (cuGetErrorString, cuMemMap, … which libggml-cuda references) must resolve
# against the driver stub libcuda.so in the toolkit's stubs dir. ggml links
# CUDA::cuda_driver but FindCUDAToolkit does not locate the stub on this CUDA-13
# sbsa base, so we force the linker explicitly. The stub's SONAME is
# libcuda.so.1, so the recorded NEEDED entry resolves at runtime to the real
# driver the Container Toolkit injects (the lane always runs with the GPU
# reserved) — the stub itself is never bundled into the runtime image.
ENV LIBRARY_PATH=/usr/local/cuda/lib64/stubs:/usr/local/cuda/targets/sbsa-linux/lib/stubs
ARG STUB=/usr/local/cuda/targets/sbsa-linux/lib/stubs

# Mirror the dogfood box's proven flags (CMakeCache.txt): CUDA on, flash-attn,
# CUDA graphs, size-optimised compression. Build only the server target + libs.
RUN cmake -B build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_CUDA=ON \
        -DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCH} \
        -DGGML_CUDA_FA=ON \
        -DGGML_CUDA_GRAPHS=ON \
        -DGGML_CUDA_COMPRESSION_MODE=size \
        -DLLAMA_CURL=ON \
        -DLLAMA_BUILD_TESTS=OFF \
        -DLLAMA_BUILD_EXAMPLES=OFF \
        -DCUDA_cuda_driver_LIBRARY=${STUB}/libcuda.so \
        -DCMAKE_SHARED_LINKER_FLAGS="-Wl,--no-as-needed -L${STUB} -lcuda" \
        -DCMAKE_EXE_LINKER_FLAGS="-L${STUB} -lcuda" \
    && cmake --build build --target llama-server -j"$(nproc)"

FROM nvidia/cuda:${CUDA_TAG}-runtime-ubuntu24.04 AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libcurl4 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --uid 10001 orionfold

# The server binary + the ggml/llama shared objects it dlopens.
COPY --from=build /src/build/bin/llama-server /usr/local/bin/llama-server
COPY --from=build /src/build/bin/*.so* /usr/local/lib/
RUN ldconfig

ENV LD_LIBRARY_PATH=/usr/local/lib
USER orionfold
EXPOSE 8091

# The model store is mounted read-only at /models by the Compose bundle; the
# lane command (model path, -ngl, -c, --jinja) is supplied by compose.py so the
# resident GGUF + knobs stay configurable without a rebuild.
ENTRYPOINT ["llama-server"]
CMD ["--host", "0.0.0.0", "--port", "8091"]
