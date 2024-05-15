import librosa
import time
import tensorflow as tf
from utils.image_transforms import unnormalize_data
from pathlib import Path
from matplotlib import pyplot as plt

class BaseGAN:
    def __init__(self, generator, discriminator, gen_optimizer, disc_optimizer, loss_fn=None):
        self.generator = generator
        self.discriminator = discriminator
        self.gen_optimizer = gen_optimizer
        self.disc_optimizer = disc_optimizer
        self.loss_fn = loss_fn
        self._generated_image_dir = None
        self._checkpoint_dir = None
        self._log_dir = None

        self.checkpoint = tf.train.Checkpoint(generator_optimizer=self.gen_optimizer,
                                    discriminator_optimizer=self.disc_optimizer,
                                    generator=self.generator,
                                    discriminator=self.discriminator)

        self._disc_loss = tf.keras.metrics.Mean(name='disc_loss')
        self._gen_loss = tf.keras.metrics.Mean(name='gen_loss')
        self._disc_accuracy = tf.keras.metrics.BinaryAccuracy(name='discriminator_accuracy')

    @property
    def generated_image_dir(self):
        return self._generated_image_dir

    @generated_image_dir.setter
    def generated_image_dir(self, generated_image_dir):
        """ Defines the directory where tensorflow checkpoint files can be stored

            Args:
                generated_image_dir: str or Path
                    Path to the directory

        """
        if isinstance(generated_image_dir, Path):
            self._generated_image_dir = generated_image_dir
        else:
            self._generated_image_dir = Path(generated_image_dir)

        self.generated_image_dir.mkdir(parents=True, exist_ok=True)

    @property
    def checkpoint_dir(self):
        return self._checkpoint_dir

    @checkpoint_dir.setter
    def checkpoint_dir(self, checkpoint_dir):
        """ Defines the directory where tensorflow checkpoint files can be stored

            Args:
                checkpoint_dir: str or Path
                    Path to the directory

        """
        if isinstance(checkpoint_dir, Path):
            self._checkpoint_dir = checkpoint_dir
        else:
            self._checkpoint_dir = Path(checkpoint_dir)

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Setup the checkpoint manager now that we know where the checkpoints will be stored
        self.ckpt_manager = tf.train.CheckpointManager(self.checkpoint, directory=str(self.checkpoint_dir), max_to_keep=4)

    @property
    def log_dir(self):
        return self._log_dir

    @log_dir.setter
    def log_dir(self, log_dir):
        """ Defines the directory where tensorflow checkpoint files can be stored

            Args:
                log_dir: str or Path
                    Path to the directory

        """
        if isinstance(log_dir, Path):
            self._log_dir = log_dir
        else:
            self._log_dir = Path(log_dir)

        self.log_dir.mkdir(parents=True, exist_ok=True)

    def generator_loss(self, fake_output):
        raise NotImplementedError

    def discriminator_loss(self, real_output, fake_output):
        raise NotImplementedError

    def train_step(self, input):
        raise NotImplementedError

    def train_loop(self, batch_generator, epochs, checkpoint_freq=5, noise_vector=None):
        generator_losses = []
        discriminator_losses = []
        discriminator_accuracies = []
        
        noise_dim = 100
        num_examples_to_generate = 16
        noise = noise_vector

        for epoch in range(epochs):
            start = time.time()
            self._gen_loss.reset_states()
            self._disc_loss.reset_states()
            self._disc_accuracy.reset_states()

            for _ in range(batch_generator.n_batches):
                # Fetch a batch of data
                train_X, _ = next(batch_generator)
                self.train_step(train_X, noise_dim)
            
            avg_gen_loss = self._gen_loss.result().numpy()
            avg_disc_loss = self._disc_loss.result().numpy()
            avg_disc_accuracy = self._disc_accuracy.result().numpy()

            print(f'Epoch {epoch + 1}, Avg Gen Loss={avg_gen_loss:.4f}, Avg Disc Loss={avg_disc_loss:.4f}, Disc Accuracy={avg_disc_accuracy:.4f}')
            
            # Append the average losses for plotting later
            generator_losses.append(avg_gen_loss)
            discriminator_losses.append(avg_disc_loss)
            discriminator_accuracies.append(avg_disc_accuracy)

            if noise_vector is None:
                noise = tf.random.normal([num_examples_to_generate, noise_dim]) 
                
            # Produce images for the GIF as you go
            self.generate_and_plot_images(self.generator, epoch + 1, noise)
            
            if (epoch + 1) % checkpoint_freq == 0:
                self.ckpt_manager.save(checkpoint_number=epoch + 1)

            print(f'Time for epoch {epoch + 1} is {time.time() - start} sec')

        # Generate after the final epoch
        self.generate_and_plot_images(self.generator, epochs, noise)
        
        if self.log_dir is not None:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10))

            # Loss plot
            ax1.plot(range(1, epochs + 1), generator_losses, label="Generator Loss")
            ax1.plot(range(1, epochs + 1), discriminator_losses, label="Discriminator Loss")
            ax1.set_title("Average Loss Over Epochs")
            ax1.set_xlabel("Epoch")
            ax1.set_ylabel("Loss")
            ax1.legend()

            # Accuracy plot
            ax2.plot(range(1, epochs + 1), discriminator_accuracies, color='orange', label="Discriminator Accuracy")
            ax2.set_title("Discriminator Accuracy Over Epochs")
            ax2.set_xlabel("Epoch")
            ax2.set_ylabel("Accuracy")
            ax2.legend()
            ax2.set_ylim(0, 1)

            plt.tight_layout()
            plt.savefig(self.log_dir / 'training_metrics.png')

    def save(self, output_dir, save_discriminator=True):
        if isinstance(output_dir, Path):
            output_dir = output_dir
        else:
            output_dir = Path(output_dir)
            # Save the generator model
        self.generator.save(output_dir / 'generator_model')
        
        # Optionally save the discriminator model
        if save_discriminator:
            self.discriminator.save(output_dir / 'discriminator_model')

    def generate_new(self, num_samples=10):
        """ Generate new spectrograms using the generator """
        # Assumes generator expects a random noise vector as input
        noise_dim = 100  
        random_noise = tf.random.normal([num_samples, noise_dim])
        
        generated_images = self.generator(random_noise, training=False)
        return generated_images

    def generate_and_plot_images(self, model, epoch, input):
        predictions = model(input, training=False)
        fig, axs = plt.subplots(4, 4, figsize=(34, 28))
        plt.subplots_adjust(wspace=0, hspace=0)  # Adjust as needed
        for i in range(predictions.shape[0]):
            ax = axs[i // 4, i % 4]
            mel_spectrogram = unnormalize_data(predictions[i, :, :, 0].numpy())
            ax.imshow(mel_spectrogram, aspect='auto', origin='lower', cmap='viridis')
            ax.axis("off")
        plt.tight_layout()
        plt.savefig(self.generated_image_dir / 'image_at_epoch_{:04d}.png'.format(epoch))
        plt.close(fig)
