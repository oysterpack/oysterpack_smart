import unittest
from dataclasses import dataclass

from oysterpack.core.command import Command


@dataclass
class AddArgs:
    a: int
    b: int


class Add(Command[AddArgs, int]):
    def __call__(self, args: AddArgs) -> int:
        return args.a + args.b


class MyTestCase(unittest.TestCase):
    def test_command(self):
        add = Add()
        self.assertEqual(add(AddArgs(1, 2)), 3)


if __name__ == "__main__":
    unittest.main()
