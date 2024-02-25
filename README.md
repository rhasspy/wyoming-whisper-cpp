# Wyoming Whisper.cpp

[Wyoming protocol](https://github.com/rhasspy/wyoming) server for the [whisper.cpp](https://github.com/ggerganov/whisper.cpp) speech to text system.

## Home Assistant Add-on

[![Show add-on](https://my.home-assistant.io/badges/supervisor_addon.svg)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=core_whisper)

[Source](https://github.com/home-assistant/addons/tree/master/whisper)

## Local Install

Install dependencies:

```sh
sudo apt-get install build-essential
```

Clone the repository and set up Python virtual environment:

``` sh
git clone https://github.com/rhasspy/wyoming-whisper-cpp.git
cd wyoming-whisper-cpp
script/setup
```

Build the whisper.cpp `main` executable:

```sh
make -C whisper.cpp/ main
```

Run a server anyone can connect to:
```sh
script/run \
  --whisper-cpp-dir ./whisper.cpp \
  --model tiny.en-q5_1 \
  --language en \
  --uri 'tcp://0.0.0.0:10300' \
  --data-dir /data \
  --download-dir /data
```

## Docker Image

``` sh
docker run -it -p 10300:10300 -v /path/to/local/data:/data rhasspy/wyoming-whisper-cpp \
    --model tiny.en-q5_1 --language en
```

[Source](https://github.com/rhasspy/wyoming-addons/tree/master/whisper-cpp)
