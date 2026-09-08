package com.example.orders;

import java.util.List;
import com.example.repo.OrderRepository;

public class OrderService extends BaseService implements Runnable, AutoCloseable {
    private final OrderRepository repo;
    private int retries;

    public OrderService(OrderRepository repo) {
        this.repo = repo;
    }

    public List<Order> findOpen(String customerId) {
        List<Order> all = repo.findByCustomer(customerId);
        Validator.check(all);
        return filterOpen(all);
    }

    private static List<Order> filterOpen(List<Order> in) {
        return in.stream().filter(Order::isOpen).toList();
    }

    @Override public void run() { new Worker(repo).start(); }
    @Override public void close() {}
}

interface Order { boolean isOpen(); }
enum Status { OPEN, CLOSED }
record Worker(OrderRepository repo) { void start() {} }
