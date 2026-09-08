package org.sample.clients;

public class Codec {
    public void encode(Options options, int size) {}

    public static class Options {
        int level;
    }

    static class Builder {
        int level;
    }
}
