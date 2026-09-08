package org.sample.core;

import java.util.List;
import org.sample.clients.Codec;
import org.sample.clients.Codec.Options;
import static org.sample.clients.Limits.MAX_SIZE;

public class Engine extends BaseEngine implements Runnable {
    private final Codec codec;
    private List<String> names;

    public Engine(Codec codec) {
        this.codec = codec;
    }

    public void run() {
        Options options = new Options();
        codec.encode(options, MAX_SIZE);
    }

    static class Builder {
        Codec codec;
    }
}

class BaseEngine {
    void start() {}
}
