from entities import Character


def make_new_round():
    return [
        Character("YOU", "blue", (100, 350), True),
        Character("ALLY", "blue", (145, 430), skill=1),
        Character("ENEMY 1", "red", (860, 250), skill=1),
        Character("ENEMY 2", "red", (860, 470), skill=2),
    ], []
