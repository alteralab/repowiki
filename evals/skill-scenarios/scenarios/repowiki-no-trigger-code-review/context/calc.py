def add(a, b):
    return a + b


def divide(a, b):
    return a / b


def average(xs):
    total = 0
    for x in xs:
        total = total + x
    return total / len(xs)
