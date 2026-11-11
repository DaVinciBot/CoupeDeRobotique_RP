// Sur PC il n'y a pas d'interruption : le bloc atomique ne fait rien
#ifndef FAKE_ATOMIC_H
#define FAKE_ATOMIC_H

#define ATOMIC_RESTORESTATE
#define ATOMIC_BLOCK(type)

#endif  // FAKE_ATOMIC_H
